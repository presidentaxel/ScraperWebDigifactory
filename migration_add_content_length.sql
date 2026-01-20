-- Migration: Add content_length column to cto_pages table
-- Run this in your Supabase SQL editor if the column doesn't exist

ALTER TABLE cto_pages 
ADD COLUMN IF NOT EXISTS content_length INTEGER;

COMMENT ON COLUMN cto_pages.content_length IS 'Size of HTML content in bytes';

