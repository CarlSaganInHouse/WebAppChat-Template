"""
Smart Home function definitions for OpenAI function calling.
Direct integration with Home Assistant (no n8n required).
"""

import os
import requests
import logging

logger = logging.getLogger(__name__)

# Home Assistant Configuration
HA_URL = os.getenv("HOME_ASSISTANT_URL", "http://${HOME_ASSISTANT_IP}:8123")
HA_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI2MGMwN2I4MDdhMTg0M2FiYWE0ZmMzNzk0OTM2ZGRiNyIsImlhdCI6MTc2NTQxMDM2OSwiZXhwIjoyMDgwNzcwMzY5fQ.NSG-U40qhjx2Cp9qZO0zL4nMaL7I0KGfTzNl-xCaDhg")
HA_TIMEOUT = int(os.getenv("HOME_ASSISTANT_TIMEOUT", "10"))

# Room name to entity_id mapping
ROOM_MAPPING = {
    'living room': 'group.living_room',
    'living_room': 'group.living_room',
    'living room 2': 'light.light_2_3',
    'living_room_2': 'light.light_2_3',
    'living room light 2': 'light.light_2_3',
    'dining room': 'group.dining_room',
    'dining_room': 'group.dining_room',
    'dining room 2': 'light.light_2_2',
    'dining_room_2': 'light.light_2_2',
    'kitchen': 'light.light_2',
    'entryway': 'light.light',
    'entry': 'light.light',
    'downstairs': 'group.downstairs_all',
    'downstairs lights': 'group.downstairs_all',
    'downstairs lighting': 'group.downstairs_all',
    'all': 'group.downstairs_all',
    'downstairs all': 'group.downstairs_all',
    'downstairs_all': 'group.downstairs_all',
    'lab': 'light.lab_hutch_light',
    'lab hutch': 'light.lab_hutch_light',
    'lamp': 'light.lamp',
    'porch': 'group.porch_all',
    'porch all': 'group.porch_all',
    'porch_all': 'group.porch_all',
    'front porch': 'group.front_porch',
    'front porch 2': 'light.front_porch_floodlight_2',
    'back porch': 'group.back_porch',
    'back porch 2': 'light.back_porch_floodlight_2',
}

# Scene name to entity_id mapping
SCENE_MAPPING = {
    'amber bloom': 'scene.downstairs_amber_bloom',
    "baby's breath": 'scene.downstairs_baby_s_breath',
    'babys breath': 'scene.downstairs_baby_s_breath',
    'blossom': 'scene.downstairs_blossom',
    'bright': 'scene.downstairs_bright',
    'chinatown': 'scene.downstairs_chinatown',
    'concentrate': 'scene.downstairs_concentrate',
    'crystalline': 'scene.downstairs_crystalline',
    'dreamy dusk': 'scene.downstairs_dreamy_dusk',
    'frosty dawn': 'scene.downstairs_frosty_dawn',
    'memento': 'scene.downstairs_memento',
    "nature's colors": 'scene.downstairs_nature_s_colors_2',
    'nature colors': 'scene.downstairs_nature_s_colors_2',
    'nighttime': 'scene.downstairs_nighttime',
    'pensive': 'scene.downstairs_pensive',
    'warriors': 'scene.downstairs_warriors',
}

# Thermostat name to entity_id mapping
THERMOSTAT_MAPPING = {
    'thermostat': 'climate.thermostat',
    'ecobee': 'climate.thermostat',
    'house': 'climate.thermostat',
    'home': 'climate.thermostat',
}

# Smart plug name to entity_id mapping
PLUG_MAPPING = {
    'tree lights': 'switch.treelights',
    'tree': 'switch.treelights',
    'christmas tree': 'switch.treelights',
    'christmas tree lights': 'switch.treelights',
    'christmas lights': 'switch.treelights',
    'table lamp': 'switch.lamp',
    'upstairs lamp': 'switch.lamp',
    'lamp plug': 'switch.lamp',
}


def get_smarthome_functions():
    """
    Generate SMARTHOME_FUNCTIONS for LLM function calling.
    """
    return [
        {
            "name": "control_lights",
            "description": "Control lights in a room (turn on/off, set brightness, change color).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["turn_on", "turn_off", "set_brightness", "toggle", "activate_scene"],
                        "description": "The action to perform"
                    },
                    "target": {
                        "type": "string",
                        "description": "Room or light to control (e.g., 'living room', 'kitchen', 'all', 'downstairs')"
                    },
                    "brightness": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Brightness percentage (0-100), only used with turn_on or set_brightness"
                    },
                    "scene": {
                        "type": "string",
                        "description": "Scene name to activate (e.g., 'relax', 'concentrate', 'christmas')"
                    }
                },
                "required": ["action", "target"]
            }
        },
        {
            "name": "get_light_status",
            "description": "Get current status of lights in a room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Room to check (e.g., 'living room', 'all'). Defaults to 'all'."
                    }
                }
            }
        },
        {
            "name": "control_thermostat",
            "description": "Control thermostat settings (temperature, mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["set_temperature", "set_mode", "set_fan"],
                        "description": "The action to perform"
                    },
                    "temperature": {
                        "type": "number",
                        "minimum": 45,
                        "maximum": 92,
                        "description": "Target temperature in Fahrenheit (45-92)"
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["off", "heat", "cool", "heat_cool"],
                        "description": "HVAC mode to set"
                    },
                    "fan_mode": {
                        "type": "string",
                        "enum": ["on", "auto"],
                        "description": "Fan mode (on = always running, auto = only when heating/cooling)"
                    },
                    "target": {
                        "type": "string",
                        "description": "Thermostat to control (e.g., 'thermostat', 'ecobee'). Defaults to main thermostat."
                    }
                },
                "required": ["action"]
            }
        },
        {
            "name": "get_thermostat_status",
            "description": "Get current thermostat status including temperature and mode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Thermostat to check (e.g., 'thermostat', 'ecobee'). Defaults to main thermostat."
                    }
                }
            }
        },
        {
            "name": "control_plug",
            "description": "Control a smart plug (turn on/off). Use for Christmas lights, lamps, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["turn_on", "turn_off", "toggle"],
                        "description": "The action to perform"
                    },
                    "target": {
                        "type": "string",
                        "description": "Plug to control (e.g., 'tree lights', 'christmas tree', 'table lamp', 'upstairs lamp')"
                    }
                },
                "required": ["action", "target"]
            }
        },
        {
            "name": "get_plug_status",
            "description": "Get current status of a smart plug.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "Plug to check (e.g., 'tree lights', 'table lamp', 'all'). Defaults to 'all'."
                    }
                }
            }
        }
    ]


# Generate the functions list
SMARTHOME_FUNCTIONS = get_smarthome_functions()


def _call_ha_service(service: str, data: dict) -> dict:
    """
    Call a Home Assistant service.
    
    Args:
        service: Service to call (e.g., 'light/turn_on', 'scene/turn_on')
        data: Service data (e.g., {'entity_id': 'light.living_room'})
    
    Returns:
        dict with success/error info
    """
    url = f"{HA_URL}/api/services/{service}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Calling HA service: {service} with data: {data}")
        response = requests.post(url, json=data, headers=headers, timeout=HA_TIMEOUT)
        
        if response.status_code == 200:
            return {"success": True, "response": response.json() if response.text else {}}
        else:
            return {"success": False, "error": f"HA returned {response.status_code}: {response.text[:200]}"}
            
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Timeout connecting to Home Assistant"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Could not connect to Home Assistant"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_ha_state(entity_id: str) -> dict:
    """
    Get the state of an entity from Home Assistant.
    """
    url = f"{HA_URL}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=HA_TIMEOUT)
        if response.status_code == 200:
            return {"success": True, "state": response.json()}
        else:
            return {"success": False, "error": f"Could not get state: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_smarthome_function(function_name: str, arguments: dict) -> dict:
    """
    Execute a smart home function based on AI function call.

    Args:
        function_name: Name of the function to execute
        arguments: Dictionary of function arguments

    Returns:
        dict: Result of the function execution with 'success' and 'message' keys
    """
    logger.info(f"Executing smart home function: {function_name} with args: {arguments}")

    if function_name == "control_lights":
        return _control_lights(arguments)
    elif function_name == "get_light_status":
        return _get_light_status(arguments)
    elif function_name == "control_thermostat":
        return _control_thermostat(arguments)
    elif function_name == "get_thermostat_status":
        return _get_thermostat_status(arguments)
    elif function_name == "control_plug":
        return _control_plug(arguments)
    elif function_name == "get_plug_status":
        return _get_plug_status(arguments)
    else:
        return {"success": False, "message": f"❌ Unknown smart home function: {function_name}"}


def _control_lights(arguments: dict) -> dict:
    """
    Control lights directly via Home Assistant API.
    """
    action = arguments.get("action", "turn_on")
    target = arguments.get("target", "downstairs")
    brightness = arguments.get("brightness")
    scene = arguments.get("scene")

    # Normalize target name
    normalized_target = target.lower().strip()
    
    # Handle scene activation
    if action == "activate_scene" and scene:
        normalized_scene = scene.lower().strip()
        scene_id = SCENE_MAPPING.get(normalized_scene, f"scene.{normalized_scene.replace(' ', '_')}")
        
        result = _call_ha_service("scene/turn_on", {"entity_id": scene_id})
        
        if result["success"]:
            return {"success": True, "message": f"💡 Activated {scene} scene"}
        else:
            return {"success": False, "message": f"❌ Failed to activate scene: {result['error']}"}
    
    # Get entity_id for the target
    entity_id = ROOM_MAPPING.get(normalized_target, f"light.{normalized_target.replace(' ', '_')}")
    
    # Build service call data
    data = {"entity_id": entity_id}
    
    if action == "turn_on":
        service = "light/turn_on"
        if brightness is not None:
            data["brightness_pct"] = max(0, min(100, brightness))
            msg = f"💡 Turned on {target} at {brightness}% brightness"
        else:
            msg = f"💡 Turned on {target}"
            
    elif action == "turn_off":
        service = "light/turn_off"
        msg = f"💡 Turned off {target}"
        
    elif action == "set_brightness":
        service = "light/turn_on"
        data["brightness_pct"] = max(0, min(100, brightness or 50))
        msg = f"💡 Set {target} brightness to {data['brightness_pct']}%"
        
    elif action == "toggle":
        service = "light/toggle"
        msg = f"💡 Toggled {target}"
        
    else:
        return {"success": False, "message": f"❌ Unknown action: {action}"}
    
    # Call Home Assistant
    result = _call_ha_service(service, data)
    
    if result["success"]:
        return {"success": True, "message": msg}
    else:
        return {"success": False, "message": f"❌ Failed: {result['error']}"}


def _get_light_status(arguments: dict) -> dict:
    """
    Get current light status from Home Assistant.
    """
    target = arguments.get("target", "all")
    normalized_target = target.lower().strip()
    
    # If asking about all lights, check downstairs (main group)
    if normalized_target in ("all", "downstairs"):
        entities_to_check = [
            ("Living Room", "light.living_room_lights"),
            ("Kitchen", "light.kitchen"),
            ("Dining Room", "light.dining_room"),
            ("Entryway", "light.entryway"),
        ]
    else:
        entity_id = ROOM_MAPPING.get(normalized_target, f"light.{normalized_target.replace(' ', '_')}")
        entities_to_check = [(target.title(), entity_id)]
    
    status_lines = []
    for name, entity_id in entities_to_check:
        result = _get_ha_state(entity_id)
        if result["success"]:
            state = result["state"]
            is_on = state.get("state") == "on"
            brightness = state.get("attributes", {}).get("brightness")
            
            if is_on:
                if brightness:
                    pct = round(brightness / 255 * 100)
                    status_lines.append(f"• {name}: ON ({pct}%)")
                else:
                    status_lines.append(f"• {name}: ON")
            else:
                status_lines.append(f"• {name}: OFF")
        else:
            status_lines.append(f"• {name}: Unknown")
    
    return {
        "success": True,
        "message": "💡 Light Status:\n" + "\n".join(status_lines)
    }


def _control_thermostat(arguments: dict) -> dict:
    """
    Control thermostat via Home Assistant API.
    """
    action = arguments.get("action", "set_temperature")
    temperature = arguments.get("temperature")
    mode = arguments.get("mode")
    fan_mode = arguments.get("fan_mode")
    target = arguments.get("target", "thermostat")

    # Get entity_id for the target
    normalized_target = target.lower().strip()
    entity_id = THERMOSTAT_MAPPING.get(normalized_target, "climate.thermostat")

    if action == "set_temperature":
        if temperature is None:
            return {"success": False, "message": "❌ Temperature is required for set_temperature action"}

        # Clamp temperature to valid range
        temperature = max(45, min(92, temperature))

        data = {"entity_id": entity_id, "temperature": temperature}
        result = _call_ha_service("climate/set_temperature", data)

        if result["success"]:
            return {"success": True, "message": f"🌡️ Set thermostat to {temperature}°F"}
        else:
            return {"success": False, "message": f"❌ Failed to set temperature: {result['error']}"}

    elif action == "set_mode":
        if mode is None:
            return {"success": False, "message": "❌ Mode is required for set_mode action"}

        data = {"entity_id": entity_id, "hvac_mode": mode}
        result = _call_ha_service("climate/set_hvac_mode", data)

        if result["success"]:
            mode_names = {
                "off": "off",
                "heat": "heating mode",
                "cool": "cooling mode",
                "heat_cool": "auto mode"
            }
            return {"success": True, "message": f"🌡️ Switched thermostat to {mode_names.get(mode, mode)}"}
        else:
            return {"success": False, "message": f"❌ Failed to set mode: {result['error']}"}

    elif action == "set_fan":
        if fan_mode is None:
            return {"success": False, "message": "❌ Fan mode is required for set_fan action"}

        data = {"entity_id": entity_id, "fan_mode": fan_mode}
        result = _call_ha_service("climate/set_fan_mode", data)

        if result["success"]:
            fan_desc = "always on" if fan_mode == "on" else "auto"
            return {"success": True, "message": f"🌡️ Set thermostat fan to {fan_desc}"}
        else:
            return {"success": False, "message": f"❌ Failed to set fan mode: {result['error']}"}

    else:
        return {"success": False, "message": f"❌ Unknown thermostat action: {action}"}


def _get_thermostat_status(arguments: dict) -> dict:
    """
    Get current thermostat status from Home Assistant.
    """
    target = arguments.get("target", "thermostat")
    normalized_target = target.lower().strip()
    entity_id = THERMOSTAT_MAPPING.get(normalized_target, "climate.thermostat")

    result = _get_ha_state(entity_id)

    if not result["success"]:
        return {"success": False, "message": f"❌ Could not get thermostat status: {result['error']}"}

    state = result["state"]
    attrs = state.get("attributes", {})

    # Extract values
    current_temp = attrs.get("current_temperature", "Unknown")
    target_temp = attrs.get("temperature", "Not set")
    humidity = attrs.get("current_humidity", "Unknown")
    hvac_mode = state.get("state", "Unknown")
    hvac_action = attrs.get("hvac_action", "idle")
    fan_mode = attrs.get("fan_mode", "Unknown")

    # Format HVAC mode for display
    mode_display = {
        "off": "Off",
        "heat": "Heat",
        "cool": "Cool",
        "heat_cool": "Auto"
    }.get(hvac_mode, hvac_mode.title())

    # Format HVAC action for display
    action_display = {
        "idle": "idle",
        "heating": "heating",
        "cooling": "cooling",
        "fan": "fan running"
    }.get(hvac_action, hvac_action)

    # Build status message
    status_lines = [
        f"• Current: {current_temp}°F",
        f"• Target: {target_temp}°F",
        f"• Humidity: {humidity}%",
        f"• Mode: {mode_display} ({action_display})",
        f"• Fan: {fan_mode.title()}"
    ]

    return {
        "success": True,
        "message": "🌡️ Thermostat Status:\n" + "\n".join(status_lines)
    }


def _control_plug(arguments: dict) -> dict:
    """
    Control smart plugs via Home Assistant API.
    """
    action = arguments.get("action", "turn_on")
    target = arguments.get("target", "")

    if not target:
        return {"success": False, "message": "❌ Target plug is required"}

    # Normalize target name
    normalized_target = target.lower().strip()

    # Get entity_id for the target
    entity_id = PLUG_MAPPING.get(normalized_target)

    if not entity_id:
        available = ", ".join(PLUG_MAPPING.keys())
        return {"success": False, "message": f"❌ Unknown plug: {target}. Available: {available}"}

    # Determine friendly name for response
    if "tree" in normalized_target or "christmas" in normalized_target:
        friendly_name = "Christmas tree lights"
    else:
        friendly_name = "table lamp"

    # Build service call
    data = {"entity_id": entity_id}

    if action == "turn_on":
        service = "switch/turn_on"
        msg = f"🔌 Turned on {friendly_name}"
    elif action == "turn_off":
        service = "switch/turn_off"
        msg = f"🔌 Turned off {friendly_name}"
    elif action == "toggle":
        service = "switch/toggle"
        msg = f"🔌 Toggled {friendly_name}"
    else:
        return {"success": False, "message": f"❌ Unknown action: {action}"}

    # Call Home Assistant
    result = _call_ha_service(service, data)

    if result["success"]:
        return {"success": True, "message": msg}
    else:
        return {"success": False, "message": f"❌ Failed: {result['error']}"}


def _get_plug_status(arguments: dict) -> dict:
    """
    Get current smart plug status from Home Assistant.
    """
    target = arguments.get("target", "all")
    normalized_target = target.lower().strip()

    # Determine which plugs to check
    if normalized_target == "all":
        plugs_to_check = [
            ("Christmas Tree Lights", "switch.treelights"),
            ("Table Lamp", "switch.lamp"),
        ]
    elif "tree" in normalized_target or "christmas" in normalized_target:
        plugs_to_check = [("Christmas Tree Lights", "switch.treelights")]
    elif "lamp" in normalized_target:
        plugs_to_check = [("Table Lamp", "switch.lamp")]
    else:
        entity_id = PLUG_MAPPING.get(normalized_target)
        if entity_id:
            plugs_to_check = [(target.title(), entity_id)]
        else:
            return {"success": False, "message": f"❌ Unknown plug: {target}"}

    status_lines = []
    for name, entity_id in plugs_to_check:
        result = _get_ha_state(entity_id)
        if result["success"]:
            state = result["state"]
            is_on = state.get("state") == "on"
            status_lines.append(f"• {name}: {'ON' if is_on else 'OFF'}")
        else:
            status_lines.append(f"• {name}: Unknown")

    return {
        "success": True,
        "message": "🔌 Smart Plug Status:\n" + "\n".join(status_lines)
    }
