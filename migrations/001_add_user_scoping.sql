-- Migration 001: Add user scoping to chats table
-- Adds user_id column to chats table to enable per-user chat history

-- Add user_id column to chats table
ALTER TABLE chats ADD COLUMN user_id INTEGER REFERENCES users(id);

-- Backfill existing chats to first user (Aaron, user_id=1)
-- This assumes Aaron is the first/only user currently
UPDATE chats SET user_id = (SELECT MIN(id) FROM users) WHERE user_id IS NULL;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id);

-- Note: SQLite doesn't support ALTER COLUMN to add NOT NULL constraint
-- The application code will enforce user_id is required for new chats
