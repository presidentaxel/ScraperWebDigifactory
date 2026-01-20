-- Migration to fix unique constraint on cto_pages
-- The current constraint UNIQUE(run_id, page_type) causes pages from different nr to overwrite each other
-- because all nr share the same run_id within a run.
-- Solution: Change to UNIQUE(nr, page_type) so each nr has its own pages

-- Step 1: Drop the old unique constraint
ALTER TABLE cto_pages DROP CONSTRAINT IF EXISTS cto_pages_run_id_page_type_key;

-- Step 2: Add new unique constraint on (nr, page_type)
ALTER TABLE cto_pages ADD CONSTRAINT cto_pages_nr_page_type_key UNIQUE (nr, page_type);

-- Step 3: Optional - Clean up duplicate pages if any exist
-- This query will show duplicates (should be empty after migration):
-- SELECT nr, page_type, COUNT(*) as count 
-- FROM cto_pages 
-- GROUP BY nr, page_type 
-- HAVING COUNT(*) > 1;

-- Note: After running this migration, you may need to clean up duplicate pages manually
-- if there are any existing duplicates in the database.

