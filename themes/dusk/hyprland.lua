-- Hyprland 0.56 Lua; only window/group border colors.
-- Keep these values in sync with colors.toml.
local active_border_color = "#dea4c1"
local inactive_border_color = "#88718f"

hl.config({
  general = { col = {
    active_border = active_border_color,
    inactive_border = inactive_border_color,
  } },
  group = { col = {
    border_active = active_border_color,
    border_inactive = inactive_border_color,
  } },
})
