# WorldModel

The WorldModel is a JSON file that provides personal context to AI agents for:
- Entity recognition (people, pets, vehicles, locations)
- Custom vocabulary and aliases
- Routing rules for inbox sorting

## Setup

1. Copy `WorldModel.example.json` to `90-Meta/WorldModel.json` in your vault
2. Edit the file to add your own entities and vocabulary
3. The inbox sorting script will use this for context

## Structure

- `user`: Your name and preferences
- `vocabulary`: Custom terms and their meanings
- `entities`: People, pets, assets, locations with aliases
- `routing`: Folder mappings for inbox sorting

See the example file for the full schema.
