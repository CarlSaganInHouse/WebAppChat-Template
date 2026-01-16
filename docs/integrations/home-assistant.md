---
title: Home Assistant Integration
last_verified: 2026-01-11
verified_by: Codex
applies_to: current codebase
---

# Home Assistant Integration

WebAppChat controls Home Assistant devices directly via the REST API (no external workflow engine required).

## Required Environment Variables

Set these in `.env`:

- `HOME_ASSISTANT_URL` - Base URL for HA (e.g., `http://<ha-host>:8123`)
- `HOME_ASSISTANT_TOKEN` - Long-lived access token
- `HOME_ASSISTANT_TIMEOUT` - Request timeout in seconds (optional)

## Token Setup

1. In Home Assistant, open your user profile.
2. Create a **Long-Lived Access Token**.
3. Set `HOME_ASSISTANT_TOKEN` in `.env` and restart the app.

## Supported Tools

Available tool calls (see `smarthome_functions.py`):

- `control_lights` / `get_light_status`
- `control_plug` / `get_plug_status`
- `control_thermostat` / `get_thermostat_status`

## Entity Mappings (Current)

Mappings are defined in `smarthome_functions.py`. Update there when entity IDs change.

### Lights (ROOM_MAPPING)

| Name | Entity ID |
| --- | --- |
| living room | `group.living_room` |
| living room 2 | `light.light_2_3` |
| dining room | `group.dining_room` |
| dining room 2 | `light.light_2_2` |
| kitchen | `light.light_2` |
| entryway / entry | `light.light` |
| downstairs / downstairs lights / all | `group.downstairs_all` |
| lab / lab hutch | `light.lab_hutch_light` |
| lamp | `light.lamp` (included in `group.dining_room`) |
| porch / porch all | `group.porch_all` |
| front porch | `group.front_porch` |
| front porch 2 | `light.front_porch_floodlight_2` |
| back porch | `group.back_porch` |
| back porch 2 | `light.back_porch_floodlight_2` |

Home Assistant groups use the `group.*` domain. If you prefer to avoid groups, map these names directly to individual `light.*` entities instead.

### Scenes (SCENE_MAPPING)

| Name | Entity ID |
| --- | --- |
| amber bloom | `scene.downstairs_amber_bloom` |
| baby's breath | `scene.downstairs_baby_s_breath` |
| blossom | `scene.downstairs_blossom` |
| bright | `scene.downstairs_bright` |
| chinatown | `scene.downstairs_chinatown` |
| concentrate | `scene.downstairs_concentrate` |
| crystalline | `scene.downstairs_crystalline` |
| dreamy dusk | `scene.downstairs_dreamy_dusk` |
| frosty dawn | `scene.downstairs_frosty_dawn` |
| memento | `scene.downstairs_memento` |
| nature's colors | `scene.downstairs_nature_s_colors_2` |
| nighttime | `scene.downstairs_nighttime` |
| pensive | `scene.downstairs_pensive` |
| warriors | `scene.downstairs_warriors` |

### Thermostat (THERMOSTAT_MAPPING)

| Name | Entity ID |
| --- | --- |
| thermostat / ecobee / house / home | `climate.thermostat` |

### Plugs (PLUG_MAPPING)

| Name | Entity ID |
| --- | --- |
| tree lights / christmas tree | `switch.treelights` |
| table lamp / upstairs lamp / lamp plug | `switch.lamp` |

## API Notes

The integration calls:

- `POST /api/services/<domain>/<service>` for actions
- `GET /api/states/<entity_id>` for status

All requests include `Authorization: Bearer <HOME_ASSISTANT_TOKEN>`.

## Troubleshooting

- **401 Unauthorized**: token invalid or expired.
- **404 Not Found**: entity ID does not exist in HA.
- **Timeouts**: check `HOME_ASSISTANT_URL` and HA connectivity.
