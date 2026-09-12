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
  ('10000000-0000-0000-0000-000000000001', 'asha1', '$2b$12$Jz6ljtdSR267WU4KYu2Ff.iMunw1xEH.7xbCW2OuNFsGCB/Y79qGm', 'asha', '00000000-0000-0000-0000-000000000001'),
  ('10000000-0000-0000-0000-000000000002', 'doctor1', '$2b$12$8QnlSCBNYmnzPJ1QVxWdle7JlQ4abrnd4SYP0OWjvn6FLG3i4q7te', 'doctor', '00000000-0000-0000-0000-000000000002'),
  ('10000000-0000-0000-0000-000000000003', 'admin1', '$2b$12$plDbSBHqUBMoRt./KChz4OSI9IBIuDCibHMEJSIoTDngqzJkfBGCO', 'admin', '00000000-0000-0000-0000-000000000002')
ON CONFLICT (id) DO NOTHING;
