"""Resolve KGSL DT clock IDs through the matching GCC source/binding header."""
import re


def resolve(clocks, bindings, driver):
    ids = {int(value): name for name, value in re.findall(
        r'^#define\s+(GCC_\w+)\s+(\d+)\s*$', bindings, re.M)}
    expected = ('iface_clk', 'mem_clk', 'mem_iface_clk')
    if tuple(c['name'] for c in clocks) != expected:
        raise ValueError('unexpected KGSL IOMMU clock ordering')
    out = []
    for clock in clocks:
        if len(clock['args']) != 1 or clock['args'][0] not in ids:
            raise ValueError('unknown GCC binding')
        name = ids[clock['args'][0]]
        match = re.search(r'\[' + name + r'\]\s*=\s*&(\w+)\.clkr', driver)
        if not match:
            raise ValueError('clock ID has no branch in matching driver')
        branch = match[1]
        match = re.search(r'static struct clk_branch\s+' + branch + r'\s*=\s*\{(.*?)\n\};', driver, re.S)
        if not match:
            raise ValueError('unsupported clock branch')
        block = match[1]
        def field(name):
            m = re.search(r'\.' + name + r'\s*=\s*(0x[0-9a-fA-F]+)', block)
            if not m:
                raise ValueError('missing literal branch register')
            return int(m[1], 16)
        bit = re.search(r'\.enable_mask\s*=\s*BIT\((\d+)\)', block)
        if not bit or int(bit[1]) > 31:
            raise ValueError('unsupported branch enable mask')
        enable, halt = field('enable_reg'), field('halt_reg')
        if enable != halt or enable & 3:
            raise ValueError('unsupported split/unaligned branch')
        out.append(dict(name=clock['name'], id=clock['args'][0], offset=enable, mask=1 << int(bit[1])))
    return out
