-- =============================================================================
-- ResearchLineage — 03_audit_columns.sql
-- Audit triggers: auto-update updated_at on every row change.
-- created_at is set once at INSERT and never touched by the trigger.
-- Run AFTER 01_tables.sql
-- =============================================================================


-- =============================================================================
-- Shared trigger function
-- =============================================================================
CREATE OR REPLACE FUNCTION fn_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Guard: only fire on actual data changes
    IF row(NEW.*) IS DISTINCT FROM row(OLD.*) THEN
        NEW.updated_at = NOW();
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_set_updated_at IS
    'Sets updated_at to NOW() on UPDATE. Skips no-op updates. Attached to all tables.';


-- =============================================================================
-- Protect created_at from being changed after INSERT
-- =============================================================================
CREATE OR REPLACE FUNCTION fn_protect_created_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'created_at is immutable and cannot be changed after insert (table: %)', TG_TABLE_NAME;
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION fn_protect_created_at IS
    'Prevents created_at from being modified after initial INSERT.';


-- =============================================================================
-- Helper macro: attach both triggers to a table
-- Usage: call attach_audit_triggers('table_name');
-- =============================================================================
-- PostgreSQL doesn't have macros, so we create a procedure for convenience.
CREATE OR REPLACE PROCEDURE attach_audit_triggers(p_table TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_trigger_updated TEXT := 'trg_' || p_table || '_set_updated_at';
    v_trigger_protect TEXT := 'trg_' || p_table || '_protect_created_at';
BEGIN
    EXECUTE format(
        'CREATE OR REPLACE TRIGGER %I
         BEFORE UPDATE ON %I
         FOR EACH ROW EXECUTE FUNCTION fn_set_updated_at()',
        v_trigger_updated, p_table
    );

    EXECUTE format(
        'CREATE OR REPLACE TRIGGER %I
         BEFORE UPDATE ON %I
         FOR EACH ROW EXECUTE FUNCTION fn_protect_created_at()',
        v_trigger_protect, p_table
    );
END;
$$;


-- =============================================================================
-- Attach triggers to all 9 tables
-- =============================================================================
CALL attach_audit_triggers('authors');
CALL attach_audit_triggers('papers');
CALL attach_audit_triggers('paper_authors');
CALL attach_audit_triggers('citations');
CALL attach_audit_triggers('paper_external_ids');
CALL attach_audit_triggers('paper_embeddings');
CALL attach_audit_triggers('paper_sections');
CALL attach_audit_triggers('citation_paths');
CALL attach_audit_triggers('citation_path_nodes');


-- =============================================================================
-- Verification query — run after deployment to confirm all triggers exist
-- =============================================================================
-- SELECT tgname, relname
-- FROM pg_trigger
-- JOIN pg_class ON pg_trigger.tgrelid = pg_class.oid
-- WHERE tgname LIKE 'trg_%'
-- ORDER BY relname, tgname;
