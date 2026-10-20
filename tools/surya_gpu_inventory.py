#!/usr/bin/env python3
"""Inventory a captured SURYA device tree; never opens a device or maps MMIO."""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def cells(data):
    if len(data) % 4:
        raise ValueError('device-tree cells must be 32-bit aligned')
    return list(struct.unpack('>' + 'I' * (len(data) // 4), data))


def strings(data):
    if not data or data[-1] != 0:
        raise ValueError('unterminated device-tree string list')
    return data[:-1].decode('utf-8').split('\0')


class Tree:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.handles = {}
        self.evidence = {}
        for path in sorted(self.root.rglob('phandle')):
            value = cells(path.read_bytes())
            if len(value) != 1 or not value[0] or value[0] in self.handles:
                raise ValueError('invalid or duplicate phandle')
            self.handles[value[0]] = path.parent

    def read(self, node, prop):
        path = node / prop
        data = path.read_bytes()
        self.evidence[str(path.relative_to(self.root)).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
        return data

    def u32(self, node, prop):
        values = cells(self.read(node, prop))
        if len(values) != 1:
            raise ValueError(f'{prop} requires exactly one cell')
        return values[0]

    def path(self, node):
        return '/' + node.relative_to(self.root).as_posix()

    def references(self, node, prop, count_prop):
        values = cells(self.read(node, prop))
        result, offset = [], 0
        while offset < len(values):
            handle = values[offset]
            if handle not in self.handles:
                raise ValueError(f'unresolved {prop} provider')
            provider = self.handles[handle]
            self.read(provider, 'phandle')
            count = self.u32(provider, count_prop)
            if count > 4 or offset + 1 + count > len(values):
                raise ValueError(f'truncated {prop} specifier')
            result.append(dict(provider=self.path(provider), args=values[offset + 1:offset + 1 + count]))
            offset += 1 + count
        return result

    def ranges(self, node):
        # reg uses its immediate parent's cell counts, not a global assumption.
        ac = self.u32(node.parent, '#address-cells') if (node.parent / '#address-cells').exists() else 2
        sc = self.u32(node.parent, '#size-cells') if (node.parent / '#size-cells').exists() else 1
        if ac not in (1, 2) or sc not in (1, 2):
            raise ValueError('unsupported register cell layout')
        raw = cells(self.read(node, 'reg'))
        names = strings(self.read(node, 'reg-names')) if (node / 'reg-names').exists() else []
        stride = ac + sc
        if len(raw) % stride or (names and len(names) != len(raw) // stride):
            raise ValueError('register names/ranges disagree')
        result = []
        for i in range(0, len(raw), stride):
            address = int.from_bytes(struct.pack('>' + 'I' * ac, *raw[i:i + ac]), 'big')
            size = int.from_bytes(struct.pack('>' + 'I' * sc, *raw[i + ac:i + stride]), 'big')
            if not size or address + size > 1 << 64:
                raise ValueError('invalid register range')
            result.append(dict(name=names[i // stride] if names else str(i // stride), base=hex(address), size=hex(size)))
        return result

    def describe(self, node):
        result = dict(path=self.path(node), compatible=strings(self.read(node, 'compatible')), registers=self.ranges(node))
        if (node / 'status').exists():
            result['status'] = strings(self.read(node, 'status'))[0]
        if (node / 'clocks').exists():
            clocks = self.references(node, 'clocks', '#clock-cells')
            names = strings(self.read(node, 'clock-names'))
            if len(names) != len(clocks):
                raise ValueError('clock names/specifiers disagree')
            result['clocks'] = [dict(name=name, **clock) for name, clock in zip(names, clocks)]
        result['supplies'] = {}
        for prop in sorted(node.glob('*-supply')):
            handle = self.u32(node, prop.name)
            if handle not in self.handles:
                raise ValueError('unresolved supply provider')
            self.read(self.handles[handle], 'phandle')
            result['supplies'][prop.name] = self.path(self.handles[handle])
        if (node / 'interrupts').exists():
            irq = cells(self.read(node, 'interrupts'))
            if len(irq) % 3 or any(irq[i] != 0 for i in range(0, len(irq), 3)):
                raise ValueError('expected GIC SPI interrupt specifiers')
            result['interrupts'] = [dict(spi=irq[i + 1], intid=irq[i + 1] + 32, flags=irq[i + 2]) for i in range(0, len(irq), 3)]
        return result


def inventory(root):
    tree = Tree(root)
    soc = tree.root / 'soc'
    gpu = soc / 'qcom,kgsl-3d0@5000000'
    chip = tree.u32(gpu, 'qcom,chipid')
    if chip >> 8 != 0x060108:
        raise ValueError('expected measured SURYA Adreno 618 chip family')
    nodes = {name: tree.describe(soc / path) for name, path in (
        ('gpu', 'qcom,kgsl-3d0@5000000'), ('gmu', 'qcom,gmu@506a000'),
        ('gpucc', 'qcom,gpucc'), ('smmu', 'arm,smmu-kgsl@5040000'),
        ('kgsl_iommu', 'qcom,kgsl-iommu@5040000'))}
    if nodes['gpu']['registers'][0]['base'] != '0x5000000' or nodes['gpu']['status'] not in ('ok', 'okay'):
        raise ValueError('GPU register/status contract differs from measured SURYA')
    contexts = {}
    for name in ('gfx3d_user', 'gfx3d_secure'):
        node = soc / 'qcom,kgsl-iommu@5040000' / name
        contexts[name] = tree.references(node, 'iommus', '#iommu-cells')
    return dict(schema=1, board='surya', gpu='Adreno 618', chip_id=hex(chip),
                mode='captured-device-tree-only', hardware_access_performed=False,
                gpu_submission_verified=False, vulkan_verified=False, metal_verified=False,
                nodes=nodes, iommu_contexts=contexts, property_hashes=tree.evidence,
                stock_firmware_dependencies=['a630_sqe.fw', 'a618_gmu.bin', 'a615_zap'],
                missing_runtime=['XNU GPU power/clock/GMU initialization', 'GPU SMMU mappings and fault recovery',
                                 'command submission and fences', 'Turnip XNU backend', 'Metal ABI/shader/presentation integration'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('device_tree', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    report = inventory(a.device_tree)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"{report['gpu']} {report['chip_id']}: captured DT inventoried; GPU execution unverified")


if __name__ == '__main__':
    main()
