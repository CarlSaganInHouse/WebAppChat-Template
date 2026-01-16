-- Migration 002: Add user settings table
-- Creates user_settings table for per-user configuration (vault paths, RAG collections, etc.)

-- Create user_settings table
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    obsidian_vault_path TEXT,
    obsidian_shared_paths TEXT,  -- JSON array: ["path1", "path2"]
    rag_collection TEXT DEFAULT 'default',
    preferences TEXT,  -- JSON object for future settings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create trigger to auto-update updated_at
CREATE TRIGGER IF NOT EXISTS update_user_settings_timestamp
AFTER UPDATE ON user_settings
BEGIN
    UPDATE user_settings SET updated_at = CURRENT_TIMESTAMP WHERE user_id = NEW.user_id;
END;

-- Insert default settings for existing users
INSERT OR IGNORE INTO user_settings (user_id, obsidian_vault_path, rag_collection)
SELECT id, NULL, 'default' FROM users;
