-- Migration 003: Add RAG collections support
-- Adds collection and user_id columns to support per-user document collections

-- Check if documents table exists before adding columns
-- Note: This migration is safe to run even if RAG tables don't exist yet

-- Add collection column to documents table if it exists
-- We'll check in the application code if the table exists first
BEGIN;

-- Try to add columns to documents table
-- SQLite will error if table doesn't exist, which is caught by migration runner
ALTER TABLE documents ADD COLUMN collection TEXT DEFAULT 'shared';
ALTER TABLE documents ADD COLUMN user_id INTEGER REFERENCES users(id);

-- Try to add collection column to chunks table
ALTER TABLE chunks ADD COLUMN collection TEXT DEFAULT 'shared';

COMMIT;

-- Add indexes for performance (only if ALTER succeeded)
CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_chunks_collection ON chunks(collection);

-- Backfill existing documents to 'shared' collection
UPDATE documents SET collection = 'shared' WHERE collection IS NULL;
UPDATE chunks SET collection = 'shared' WHERE collection IS NULL;
