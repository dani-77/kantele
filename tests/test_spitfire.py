import shutil
import tempfile
import unittest
from pathlib import Path

from kantele.backends import luautil, spitfire

SAMPLE = """\
-- my spitfire config
spitfire.border = { width = 3, active = "#112233", inactive = "#445566", radius = 4 }
spitfire.gaps = { inner = 8, outer = 8 }
spitfire.autostart({ "waybar" })
spitfire.rule({ app_id = "pavucontrol", floating = true })
spitfire.bind("Mod4", "Return", function() spitfire.spawn("foot") end)
spitfire.bind("Mod4", "q", function() spitfire.window.close() end)
for i = 1, 3 do
  spitfire.bind("Mod4", tostring(i), function() spitfire.workspace.focus(i) end)
end
spitfire.workspace.max = 9
"""


@unittest.skipUnless(shutil.which(luautil.LUA), "needs lua5.4")
class SpitfireBackendTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name) / "spitfire"
        d.mkdir()
        self.path = d / "config.lua"
        self.path.write_text(SAMPLE)

    def tearDown(self):
        self.dir.cleanup()

    def effective(self):
        return spitfire._run_lua(self.path, skip=False)

    def test_read_base(self):
        s = spitfire.Config(self.path).read()
        self.assertEqual(s.values[("border", "width")], 3)
        self.assertEqual(s.values[("gaps", "inner")], 8)
        self.assertEqual(s.values[("bar", "height")], 24)  # default
        self.assertEqual(s.overrides(), {})
        self.assertEqual([b.combo for b in s.base_binds],
                         ["Mod4+Return", "Mod4+q", "Mod4+1", "Mod4+2", "Mod4+3"])
        self.assertTrue(s.base_binds[0].arg.startswith("line 6: spitfire.bind"))

    def test_save_overrides_and_keys(self):
        c = spitfire.Config(self.path)
        s = c.read()
        s.values[("gaps", "outer")] = 2
        s.values[("output", "scale")] = 1.5
        s.binds = [spitfire.Bind("Mod4+Return", "spawn", "alacritty -e fish"),
                   spitfire.Bind("super+q", "none"),
                   spitfire.Bind("Mod4+Shift+h", "mfact.inc", "-0.05"),
                   spitfire.Bind("Mod1+2", "workspace.move_window", "2")]
        self.assertEqual(spitfire.validate(s), [])
        self.assertEqual(c.save(s).read_text(), SAMPLE)
        self.assertIn(spitfire.LOADER_MARK, self.path.read_text())

        eff = self.effective()
        self.assertEqual(eff["settings"]["gaps"], {"inner": 8, "outer": 2})
        self.assertEqual(eff["settings"]["output"], {"scale": 1.5})
        combos = [(b["mods"], b["key"]) for b in eff["binds"]]
        self.assertNotIn(("Mod4", "q"), combos)                 # "none" unbinds
        self.assertEqual(combos.count(("Mod4", "Return")), 1)    # replaced, not doubled
        self.assertIn(("Mod1", "2"), combos)

        s2 = spitfire.Config(self.path).read()
        self.assertEqual(s2.overrides(), s.overrides())
        self.assertEqual([b.combo for b in s2.binds],
                         ["Mod4+Return", "Mod4+q", "Mod4+Shift+h", "Mod1+2"])
        self.assertEqual(s2.binds[2].arg, "-0.05")
        self.assertEqual(s2.base[("gaps", "outer")], 8)

    def test_noop_save_is_identical(self):
        c = spitfire.Config(self.path)
        s = c.read()
        s.values[("bar", "enable")] = True
        s.binds = [spitfire.Bind("Mod4+d", "spawn", "d77run")]
        c.save(s)
        cfg, ovr = self.path.read_bytes(), c.overrides_path.read_bytes()
        c2 = spitfire.Config(self.path)
        c2.save(c2.read())
        self.assertEqual(self.path.read_bytes(), cfg)
        self.assertEqual(c2.overrides_path.read_bytes(), ovr)

    def test_validate(self):
        s = spitfire.Config(self.path).read()
        s.values[("bar", "bg")] = "#11223344"   # spitfire takes #RRGGBB only
        s.binds = [spitfire.Bind("Mod4+x", "layout.set", "grid"),
                   spitfire.Bind("Hyper+x", "quit"),
                   spitfire.Bind("Mod4+y", "workspace.focus", "a"),
                   spitfire.Bind("Mod4+z", "spawn", ""),
                   spitfire.Bind("Mod4+w", "quit"), spitfire.Bind("super+w", "quit")]
        errs = "\n".join(spitfire.validate(s))
        for frag in ("#RRGGBB", "layout must be", "unknown modifier", "whole number",
                     "needs a command", "more than once"):
            self.assertIn(frag, errs)

    def test_combos(self):
        self.assertEqual(spitfire.combo_from_penrose("M-S-Return"), "Mod4+Shift+Return")
        self.assertEqual(spitfire.combo_from_penrose("C-A-t"), "Ctrl+Mod1+t")
        self.assertEqual(spitfire.normalize_combo("shift+super+Return"), "Mod4+Shift+Return")
        self.assertEqual(spitfire.normalize_combo("XF86AudioMute"), "XF86AudioMute")


if __name__ == "__main__":
    unittest.main()
