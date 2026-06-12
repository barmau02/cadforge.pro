# UI Build Skills Reference

Open-source skill repos used to guide this rebuild:

| Repo | URL | Use for |
|------|-----|---------|
| **Anthropic Frontend Design** | https://github.com/anthropics/claude-code/tree/main/plugins/frontend-design/skills/frontend-design | Distinctive typography, cohesive themes, avoid generic AI aesthetics |
| **UI/UX Pro Max** | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill | Color systems, spacing, accessibility, React patterns, 99 UX rules |
| **Awesome Claude Skills** | https://github.com/ComposioHQ/awesome-claude-skills | Curated index of agent skills |

## Design system (PromptForge)

- **Style**: Industrial utilitarian — CAD/manufacturing tool
- **Fonts**: Outfit (UI) + IBM Plex Mono (code)
- **Palette**: Dark base `#050807`, accent lime `#84cc16`
- **Layout**: Sidebar nav + top service bar + section panels

## Applying skills in Cursor/Grok

Copy a skill's `SKILL.md` into `.grok/skills/` or reference at build time:

```
Read: github.com/anthropics/claude-code/.../frontend-design/SKILL.md
Read: github.com/nextlevelbuilder/ui-ux-pro-max-skill/.../ui-ux-pro-max/SKILL.md
```

Then prompt: "Rebuild [component] following the frontend-design skill."