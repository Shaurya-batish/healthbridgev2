-- Demo seed data: facilities and users.
-- Run after Alembic migrations (services/core) have created the schema:
--   psql "$DATABASE_URL" -f scripts/seed_facilities_and_users.sql
--
-- Passwords are demo-only, already bcrypt-hashed below:
--   asha1  / asha-demo-pass
--   doctor1 / doctor-demo-pass
--   admin1 / admin-demo-pass

INSERT INTO facilities (id, name, level) VALUES
  ('00000000-0000-0000-0000-000000000001', 'Rampur Sub-Centre', 'sub_centre'),
  ('00000000-0000-0000-0000-000000000002', 'Rampur PHC', 'phc'),
  ('00000000-0000-0000-0000-000000000003', 'District Hospital - Rampur', 'district_hospital')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, username, password_hash, role, facility_id) VALUES
  ('10000000-0000-0000-0000-000000000001', 'asha1', '$2b$12$Jz6ljtdSR267WU4KYu2Ff.iMunw1xEH.7xbCW2OuNFsGCB/Y79qGm', 'asha', '00000000-0000-0000-0000-000000000002'),
  ('10000000-0000-0000-0000-000000000002', 'doctor1', '$2b$12$8QnlSCBNYmnzPJ1QVxWdle7JlQ4abrnd4SYP0OWjvn6FLG3i4q7te', 'doctor', '00000000-0000-0000-0000-000000000002'),
  ('10000000-0000-0000-0000-000000000003', 'admin1', '$2b$12$plDbSBHqUBMoRt./KChz4OSI9IBIuDCibHMEJSIoTDngqzJkfBGCO', 'admin', '00000000-0000-0000-0000-000000000002')
ON CONFLICT (id) DO NOTHING;

-- DEMO-ONLY WORKAROUND (2026-09-14), see claude/state-and-next-steps.md P1.
--
-- The data model has no referring-vs-receiving facility concept, so an
-- encounter, queue token or RED escalation created by an ASHA at the
-- sub-centre is facility-scoped to the sub-centre, where no user account
-- exists -- doctor1 sits at the PHC and therefore sees none of it. A live
-- ASHA -> doctor handoff silently fails.
--
-- Until `origin_facility_id` (or `parent_facility_id`) is built properly,
-- asha1 is attached to the PHC so the handoff is demonstrable. The UPDATE
-- below makes this idempotent: the INSERT above is ON CONFLICT DO NOTHING,
-- so on an already-seeded database it would otherwise be a no-op.
--
-- REVERT THIS (set facility back to ...0001) once P1 lands.
UPDATE users
   SET facility_id = '00000000-0000-0000-0000-000000000002'
 WHERE username = 'asha1';
