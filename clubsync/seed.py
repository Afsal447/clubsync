import os, sqlite3, json
from werkzeug.security import generate_password_hash as g
DB = os.environ.get('DB_PATH', 'campus.db')
if os.path.exists(DB): os.remove(DB)
c = sqlite3.connect(DB); c.execute('PRAGMA foreign_keys=ON'); c.executescript(open('schema.sql').read()); p = g('demo123')
U = [('super@demo.in', 'Super Admin', 'super_admin', None, None), ('admin@demo.in', 'Admin', 'admin', None, None), ('club@demo.in', 'Club Admin', 'club_admin', None, None),
     ('faculty@demo.in', 'Dr. Mentor', 'faculty', None, None), ('vol@demo.in', 'Volunteer Vee', 'student', 'RA2211003010002', 4), ('stu@demo.in', 'Student Sam', 'student', 'RA2211003010001', 4)]
for e, n, r, ra, m in U: c.execute('insert into users(email,pw,name,role,ra_number,mentor_id) values(?,?,?,?,?,?)', (e, p, n, r, ra, m))
c.execute("insert into clubs(name,description,admin_id,coordinator_id) values('Coding Club','Hack and build',3,4)")
c.execute("insert into club_roles(club_id,name,perms) values(1,'Logistics Lead',?)", (json.dumps(['event.edit']),))
c.execute("insert into club_members values(1,5,1)")
c.execute("insert into timetables values(1,'Regular Day',?, '2026-01-01',1)", ('mon,tue,wed,thu,fri',))
for i, (a, b, k) in enumerate([('08:30', '09:20', 'class'), ('09:20', '10:10', 'class'), ('10:10', '10:25', 'short_break'), ('10:25', '11:15', 'class'), ('11:15', '12:05', 'class'), ('12:05', '12:50', 'lunch'), ('12:50', '13:40', 'class'), ('13:40', '14:30', 'class')], 1):
    c.execute('insert into periods(tt_id,label,start,end,kind) values(1,?,?,?,?)', (f'Period {i}' if k == 'class' else k, a, b, k))
c.commit(); print('seeded. all passwords: demo123')
