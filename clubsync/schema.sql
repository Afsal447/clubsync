PRAGMA foreign_keys=ON;
CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, pw TEXT NOT NULL, name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN('super_admin','admin','club_admin','faculty','student')),
 ra_number TEXT UNIQUE CHECK(ra_number IS NULL OR (length(ra_number)=15 AND ra_number NOT GLOB '*[^A-Za-z0-9]*')),
 mentor_id INTEGER REFERENCES users(id),
 CHECK((role='student')=(ra_number IS NOT NULL)));
CREATE INDEX idx_users_ra ON users(ra_number);
CREATE TABLE clubs(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','archived')),
 admin_id INTEGER REFERENCES users(id), coordinator_id INTEGER REFERENCES users(id));
CREATE TABLE club_roles(id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
 name TEXT NOT NULL, perms TEXT NOT NULL DEFAULT '[]', UNIQUE(club_id,name));
CREATE TABLE club_members(club_id INTEGER NOT NULL REFERENCES clubs(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id), role_id INTEGER REFERENCES club_roles(id), PRIMARY KEY(club_id,user_id));
CREATE TABLE timetables(id INTEGER PRIMARY KEY, name TEXT NOT NULL, days TEXT NOT NULL, effective_from TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 0 CHECK(active IN(0,1)));
CREATE TABLE periods(id INTEGER PRIMARY KEY, tt_id INTEGER NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
 label TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN('class','short_break','lunch')), CHECK(end>start));
CREATE TABLE audit_log(id INTEGER PRIMARY KEY, at TEXT DEFAULT CURRENT_TIMESTAMP, user_id INTEGER, action TEXT);
CREATE TABLE events(id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id), title TEXT NOT NULL, description TEXT,
 date TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, venue TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity>=0),
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN('draft','pending','approved','rejected','ongoing','completed','cancelled')),
 reject_reason TEXT, CHECK(end>start));
CREATE TABLE registrations(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
 student_id INTEGER NOT NULL REFERENCES users(id), attended INTEGER NOT NULL DEFAULT 0, UNIQUE(event_id,student_id));
-- DB-level approval gate + capacity: even a buggy API cannot bypass these
CREATE TRIGGER reg_gate BEFORE INSERT ON registrations BEGIN
 SELECT RAISE(ABORT,'event not open for registration') WHERE (SELECT status FROM events WHERE id=NEW.event_id) NOT IN('approved','ongoing');
 SELECT RAISE(ABORT,'event is full') WHERE (SELECT count(*) FROM registrations WHERE event_id=NEW.event_id)>=(SELECT capacity FROM events WHERE id=NEW.event_id);
END;
CREATE TABLE od_requests(id INTEGER PRIMARY KEY, reg_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
 student_id INTEGER NOT NULL REFERENCES users(id), mentor_id INTEGER NOT NULL REFERENCES users(id),
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN('pending','approved','rejected')), remark TEXT,
 periods_snapshot TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP, CHECK(mentor_id<>student_id));
CREATE TABLE certificates(id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, reg_id INTEGER NOT NULL UNIQUE REFERENCES registrations(id),
 label TEXT NOT NULL, issued_by INTEGER REFERENCES users(id), issued TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE notifications(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), msg TEXT NOT NULL, read INTEGER DEFAULT 0, at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE badges(id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL REFERENCES clubs(id), name TEXT NOT NULL, UNIQUE(club_id,name));
CREATE TABLE user_badges(badge_id INTEGER NOT NULL REFERENCES badges(id), user_id INTEGER NOT NULL REFERENCES users(id), awarded_by INTEGER REFERENCES users(id), at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(badge_id,user_id));
CREATE TABLE messages(id INTEGER PRIMARY KEY, sender_id INTEGER NOT NULL REFERENCES users(id), recipient_id INTEGER NOT NULL REFERENCES users(id),
 ctx_type TEXT NOT NULL DEFAULT 'general' CHECK(ctx_type IN('general','event','od')), ctx_id INTEGER, body TEXT NOT NULL CHECK(length(body)>0), at TEXT DEFAULT CURRENT_TIMESTAMP);
