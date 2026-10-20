#!/usr/bin/env python3
"""Generate sanitized kernel GPU resources from this Poco's captured Linux DT."""
import argparse
import hashlib
import json
from pathlib import Path
from surya_gpu_inventory import Tree, cells, strings, inventory


def generate(root):
    report = inventory(root)
    tree = Tree(root)
    soc = tree.root / 'soc'
    facts = {'CHIP_ID': int(report['chip_id'], 16)}

    def region(label, node, index=0):
        value = tree.ranges(node)[index]
        facts[label + '_PA'] = int(value['base'], 16)
        facts[label + '_SIZE'] = int(value['size'], 16)

    for label, name in (('GPU', 'gpu'), ('GMU', 'gmu'), ('GPUCC', 'gpucc'), ('SMMU', 'smmu')):
        region(label, tree.root / report['nodes'][name]['path'].lstrip('/'))
    gmu = tree.root / report['nodes']['gmu']['path'].lstrip('/')
    named = {v['name']: i for i, v in enumerate(tree.ranges(gmu))}
    region('PDC_CFG', gmu, named['kgsl_gmu_pdc_cfg'])
    region('PDC_SEQ', gmu, named['kgsl_gmu_pdc_seq'])
    clocks = report['nodes']['smmu']['clocks']
    clocks = [c for c in clocks if c['name'] == 'gcc_gpu_memnoc_gfx_clk']
    if len(clocks) != 1 or len(clocks[0]['args']) != 1:
        raise ValueError('missing unique SMMU MEMNOC clock binding')
    gcc = tree.root / clocks[0]['provider'].lstrip('/')
    if 'qcom,gcc-sdmmagpie' not in strings(tree.read(gcc, 'compatible')):
        raise ValueError('unexpected Poco GCC provider')
    region('GCC', gcc)
    facts['MEMNOC_CLOCK_ID'] = clocks[0]['args'][0]
    for label, name in (('USER_SID', 'gfx3d_user'), ('SECURE_SID', 'gfx3d_secure')):
        refs = report['iommu_contexts'][name]
        if len(refs) != 1 or len(refs[0]['args']) != 1 or refs[0]['provider'] != report['nodes']['smmu']['path']:
            raise ValueError('unexpected IOMMU route')
        facts[label] = refs[0]['args'][0]
    user = soc / 'qcom,kgsl-iommu@5040000/gfx3d_user'
    offset = tree.u32(user, 'qcom,gpu-offset')
    # qcom,gpu-offset is relative to the GPU, NOT to the SMMU register base.
    facts['USER_CB_OFFSET'] = facts['GPU_PA'] + offset - facts['SMMU_PA']
    if facts['USER_CB_OFFSET'] < 0 or facts['USER_CB_OFFSET'] + 4096 > facts['SMMU_SIZE']:
        raise ValueError('context window outside SMMU')
    ac, pc, sc = (tree.u32(soc, '#address-cells'), tree.u32(tree.root, '#address-cells'), tree.u32(soc, '#size-cells'))
    raw = cells(tree.read(soc, 'ranges'))
    stride = ac + pc + sc
    if not raw or len(raw) % stride:
        raise ValueError('explicit SoC address translation required')
    def number(seq):
        return int.from_bytes(b''.join(v.to_bytes(4, 'big') for v in seq), 'big')
    translated = []
    for i in range(0, len(raw), stride):
        child = number(raw[i:i+ac]); parent = number(raw[i+ac:i+ac+pc]); span = number(raw[i+ac+pc:i+stride])
        if child != parent:
            raise ValueError('non-identity SoC translation is not supported')
        translated.append((child, span))
    for key, value in facts.items():
        if key.endswith('_PA') and not any(base <= value and value + facts[key[:-3]+'_SIZE'] <= base + size for base, size in translated):
            raise ValueError('register window outside translated SoC bus')
    evidence = dict(report['property_hashes'], **tree.evidence)
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    lines = ['/* Generated from captured SURYA DT. No device identifiers or raw dumps. */',
             '/* Property-evidence SHA256: ' + digest + ' */',
             '#ifndef SURYA_GPU_DT_H', '#define SURYA_GPU_DT_H', '#include <stdint.h>']
    lines += [f'#define SURYA_DT_{k} UINT64_C(0x{v:x})' for k, v in sorted(facts.items())]
    lines += ['#endif', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device_tree', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.write_bytes(generate(args.device_tree).encode())
    print(args.out)
