import unittest
from surya_gpu_clocks import resolve


class GpuClockBindingTests(unittest.TestCase):
    def setUp(self):
        self.clocks = [dict(name=n, args=[i]) for n, i in
                       [('iface_clk', 40), ('mem_clk', 27), ('mem_iface_clk', 43)]]
        self.bindings = '#define GCC_IFACE 40\n#define GCC_MEMORY 27\n#define GCC_NOC 43\n'
        self.driver = ''
        for symbol, branch, offset in [('GCC_IFACE', 'iface', '0x71004'),
                                      ('GCC_MEMORY', 'memory', '0x4452c'),
                                      ('GCC_NOC', 'noc', '0x7100c')]:
            self.driver += (f'static struct clk_branch {branch} = {{\n'
                            f'.halt_reg = {offset}, .enable_reg = {offset}, .enable_mask = BIT(0),\n}};\n'
                            f'[{symbol}] = &{branch}.clkr,\n')

    def test_preserves_dt_order_and_resolves_binding_not_id_as_offset(self):
        plan = resolve(self.clocks, self.bindings, self.driver)
        self.assertEqual([x['id'] for x in plan], [40, 27, 43])
        self.assertEqual([x['offset'] for x in plan], [0x71004, 0x4452c, 0x7100c])
        self.assertEqual([x['mask'] for x in plan], [1, 1, 1])

    def test_refuses_missing_or_reordered_clocks(self):
        for clocks in (self.clocks[1:], self.clocks[::-1]):
            with self.assertRaises(ValueError): resolve(clocks, self.bindings, self.driver)

    def test_refuses_unknown_id_and_split_register(self):
        self.clocks[0]['args'] = [99]
        with self.assertRaises(ValueError): resolve(self.clocks, self.bindings, self.driver)
        self.clocks[0]['args'] = [40]
        with self.assertRaises(ValueError):
            resolve(self.clocks, self.bindings, self.driver.replace('enable_reg = 0x71004', 'enable_reg = 0x71008'))

    def test_refuses_unparsed_enable_mask(self):
        with self.assertRaises(ValueError):
            resolve(self.clocks, self.bindings, self.driver.replace('BIT(0)', 'OTHER_MASK'))
