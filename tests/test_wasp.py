import shutil
import tempfile
import unittest
from pathlib import Path

from kantele.backends import wasp

SAMPLE = """\
-- my wasp config
wasp = {}
wasp.border = { width = 3, focus = "#112233", normal = "#445566" }
wasp.gaps = { inner = 6, outer = 6, smart = false }
wasp.terminal = { "foot" }
wasp.modkey = "super"
wasp.keys = {}
local keys = wasp.keys
local function bind(mods, key, action, fields)
  fields = fields or {}
  fields.mods, fields.key, fields.action = mods, key, action
  keys[#keys + 1] = fields
end
bind({ "mod", "shift" }, "Return", "spawn-terminal")
bind({ "mod" }, "r", "spawn", { cmd = { "sh", "-c", "echo 'hi there'" } })
bind({ "mod" }, "h", "setmfact", { delta = -0.05 })
for i = 1, 3 do bind({ "mod" }, tostring(i), "view", { tag = i }) end
"""


@unittest.skipUnless(shutil.which(wasp.LUA), "needs lua5.4")
class WaspBackendTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "config.lua"
        self.path.write_text(SAMPLE)

    def tearDown(self):
        self.dir.cleanup()

    def effective(self):
        return wasp._run_lua(self.path, skip=False)

    def test_read_base(self):
        s = wasp.Config(self.path).read()
        self.assertEqual(s.values[("border", "width")], 3)
        self.assertEqual(s.values[("terminal",)], ["foot"])
        self.assertEqual(s.values[("bar", "layout")], "tln|s")  # default
        self.assertEqual(s.overrides(), {})
        self.assertEqual(len(s.base_binds), 6)
        self.assertEqual(s.base_binds[1].arg, "sh -c 'echo '\"'\"'hi there'\"'\"''")
        self.assertEqual(s.base_binds[2].arg, "-0.05")

    def test_save_overrides_and_keys(self):
        c = wasp.Config(self.path)
        s = c.read()
        s.values[("gaps", "inner")] = 12
        s.values[("terminal",)] = ["alacritty", "-e", "fish"]
        s.binds = [wasp.Bind("mod+shift+Return", "spawn", "alacritty"),
                   wasp.Bind("mod+h", "none")]
        self.assertEqual(wasp.validate(s), [])
        backup = c.save(s)
        self.assertEqual(backup.read_text(), SAMPLE)
        text = self.path.read_text()
        self.assertTrue(text.startswith(SAMPLE))
        self.assertIn(wasp.LOADER_MARK, text)

        eff = self.effective()
        self.assertEqual(eff["gaps"], {"inner": 12, "outer": 6, "smart": False})
        self.assertEqual(eff["border"]["width"], 3)
        self.assertEqual(eff["terminal"], ["alacritty", "-e", "fish"])
        first = eff["keys"][:3]
        self.assertEqual(first[0]["cmd"], ["alacritty"])
        self.assertEqual(first[1]["action"], "none")
        self.assertEqual(first[2]["action"], "spawn-terminal")  # config.lua's, after ours

        s2 = wasp.Config(self.path).read()
        self.assertEqual(s2.overrides(), s.overrides())
        self.assertEqual(s2.binds, s.binds)
        self.assertEqual(s2.base[("gaps", "inner")], 6)  # base ignores kantele.lua

    def test_noop_save_is_identical(self):
        c = wasp.Config(self.path)
        s = c.read()
        s.values[("border", "focus")] = "#abcdef"
        s.binds = [wasp.Bind("super+shift+x", "spawn", "foot -e 'a b'")]
        c.save(s)
        cfg, ovr = self.path.read_bytes(), c.overrides_path.read_bytes()
        c2 = wasp.Config(self.path)
        c2.save(c2.read())
        self.assertEqual(self.path.read_bytes(), cfg)
        self.assertEqual(c2.overrides_path.read_bytes(), ovr)

    def test_back_to_base_drops_override(self):
        c = wasp.Config(self.path)
        s = c.read()
        s.values[("gaps", "outer")] = 1
        c.save(s)
        s = wasp.Config(self.path).read()
        s.values[("gaps", "outer")] = 6
        c.save(s)
        self.assertNotIn("outer", c.overrides_path.read_text())

    def test_broken_config_rolls_back(self):
        c = wasp.Config(self.path)
        s = c.read()
        s.values[("gaps", "inner")] = 2
        c.save(s)
        good = c.overrides_path.read_text()
        # config.lua broken by hand after the loader line was added
        self.path.write_text(self.path.read_text() + "\nerror('boom')\n")
        s.values[("gaps", "inner")] = 3
        with self.assertRaises(wasp.LuaError):
            c.save(s)
        self.assertEqual(c.overrides_path.read_text(), good)

    def test_validate(self):
        s = wasp.Config(self.path).read()
        s.values[("border", "focus")] = "red"
        s.binds = [wasp.Bind("mod+x", "view", "12"), wasp.Bind("hyper+x", "zoom"),
                   wasp.Bind("mod+y", "zoom"), wasp.Bind("mod+y", "zoom"),
                   wasp.Bind("mod+z", "spawn", ""), wasp.Bind("mod+m", "moveresizekb", "dx=a")]
        errs = "\n".join(wasp.validate(s))
        for frag in ("not a #RRGGBB", "workspace must be", "unknown modifier",
                     "more than once", "needs a command", "dx=.."):
            self.assertIn(frag, errs)

    def test_combos(self):
        self.assertEqual(wasp.combo_from_penrose("M-S-Return", "super"), "mod+shift+Return")
        self.assertEqual(wasp.combo_from_penrose("M-A-x", "alt"), "mod+super+x")
        self.assertEqual(wasp.normalize_combo("Shift+Control+Mod+q"), "mod+ctrl+shift+q")

    def test_lua_literal_escapes(self):
        self.assertEqual(wasp.lua_literal('a"b\\c\n'), '"a\\"b\\\\c\\n"')


if __name__ == "__main__":
    unittest.main()
