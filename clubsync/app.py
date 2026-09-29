import sqlite3, json, hmac, hashlib, time, os, re, secrets
from datetime import date as D, datetime as DT
from flask import Flask, request, session, jsonify, g
from werkzeug.security import generate_password_hash as gph, check_password_hash as cph
app = Flask(__name__, static_folder='static', static_url_path='')
@app.get('/')
def home(): return app.send_static_file('index.html')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-change-me')
DB = os.environ.get('DB_PATH', 'campus.db')
PERMS = {'event.edit', 'attendance.mark', 'cert.issue', 'members.manage'}

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db
@app.teardown_appcontext
def _close(_):
    d = g.pop('db', None)
    if d: d.close()
def q(sql, a=(), one=False):
    c = db().execute(sql, a); r = [dict(x) for x in c.fetchall()]; db().commit()
    return (r[0] if r else None) if one else r
class E(Exception):
    def __init__(s, m, c=400): s.m, s.c = m, c
@app.errorhandler(E)
def _e(e): return jsonify(error=e.m), e.c
@app.errorhandler(sqlite3.IntegrityError)
def _ie(e): return jsonify(error=str(e)), 409

def me():
    u = q('select * from users where id=?', (session.get('uid'),), True)
    if not u: raise E('login required', 401)
    return u
def need(*roles):
    u = me()
    if u['role'] not in roles: raise E('forbidden for your role', 403)
    return u
def notify(uid, msg): q('insert into notifications(user_id,msg) values(?,?)', (uid, msg))
def audit(u, a): q('insert into audit_log(user_id,action) values(?,?)', (u['id'], a))
def club_of(eid):
    ev = q('select * from events where id=?', (eid,), True)
    if not ev: raise E('no such event', 404)
    return ev
def can(u, club_id, perm):  # dynamic-role permission check, always server side
    c = q('select * from clubs where id=?', (club_id,), True)
    if not c: raise E('no such club', 404)
    if c['admin_id'] == u['id']: return True
    r = q('select r.perms from club_members m join club_roles r on r.id=m.role_id where m.club_id=? and m.user_id=?', (club_id, u['id']), True)
    if not (r and perm in json.loads(r['perms'])): raise E(f'missing permission {perm}', 403)
    return True

# ---------- auth ----------
@app.post('/api/signup')
def signup():
    d = request.json; ra = d.get('ra_number', '')
    if not re.fullmatch(r'[A-Za-z0-9]{15}', ra): raise E('RA Number must be 15 alphanumeric characters')
    m = q('select id from users where email=? and role="faculty"', (d.get('mentor_email', ''),), True)
    q('insert into users(email,pw,name,role,ra_number,mentor_id) values(?,?,?,?,?,?)',
      (d['email'].lower(), gph(d['password']), d['name'], 'student', ra.upper(), m and m['id']))
    return login()
@app.post('/api/login')
def login():
    d = request.json; u = q('select * from users where email=?', (d['email'].lower(),), True)
    if not u or not cph(u['pw'], d['password']): raise E('invalid credentials', 401)
    session['uid'] = u['id']; return jsonify(id=u['id'], name=u['name'], role=u['role'])
@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=1)
@app.get('/api/me')
def whoami(): u = me(); return jsonify(id=u['id'], name=u['name'], role=u['role'], ra=u['ra_number'])
@app.post('/api/users')
def mkuser():
    u = need('super_admin', 'admin'); d = request.json
    allowed = {'admin', 'club_admin', 'faculty'} if u['role'] == 'super_admin' else {'club_admin'}
    if d['role'] not in allowed: raise E('you cannot create this role', 403)
    q('insert into users(email,pw,name,role) values(?,?,?,?)', (d['email'].lower(), gph(d['password']), d['name'], d['role']))
    return jsonify(ok=1)

# ---------- clubs & dynamic roles ----------
@app.post('/api/clubs')
def mkclub():
    need('super_admin', 'admin'); d = request.json
    q('insert into clubs(name,description,admin_id,coordinator_id) values(?,?,?,?)', (d['name'], d.get('description'), d.get('admin_id'), d.get('coordinator_id')))
    return jsonify(ok=1)
@app.get('/api/clubs')
def clubs(): me(); return jsonify(q('select * from clubs where status="active"'))
@app.post('/api/clubs/<int:cid>/roles')
def mkrole(cid):
    u = me(); can(u, cid, 'members.manage'); d = request.json
    if not set(d['perms']) <= PERMS: raise E('unknown permission')
    q('insert into club_roles(club_id,name,perms) values(?,?,?)', (cid, d['name'], json.dumps(d['perms']))); return jsonify(ok=1)
@app.post('/api/clubs/<int:cid>/members')
def addmember(cid):
    u = me(); can(u, cid, 'members.manage'); d = request.json
    s = q('select id from users where ra_number=?', (d['ra_number'].upper(),), True)
    if not s: raise E('unknown RA Number', 404)
    q('insert or replace into club_members values(?,?,?)', (cid, s['id'], d.get('role_id')))
    notify(s['id'], 'You were added to a club / assigned a new role'); return jsonify(ok=1)

# ---------- timetable (super admin only) ----------
def mins(t): h, m = t.split(':'); return int(h) * 60 + int(m)
def validate(ps):
    prev, warn = None, []
    for p in ps:
        s, e = mins(p['start']), mins(p['end'])
        if e <= s: raise E(f"{p['label']}: end must be after start")
        if prev is not None:
            if s < prev: raise E(f"{p['label']} overlaps or precedes the previous period")
            if s > prev: warn.append(f"gap before {p['label']}")
        prev = e
    return warn
@app.post('/api/timetable')
def mktt():
    u = need('super_admin'); d = request.json; warn = validate(d['periods'])
    c = db().cursor(); c.execute('insert into timetables(name,days,effective_from,active) values(?,?,?,0)', (d['name'], d['days'], d['effective_from'])); tid = c.lastrowid
    for p in d['periods']: c.execute('insert into periods(tt_id,label,start,end,kind) values(?,?,?,?,?)', (tid, p['label'], p['start'], p['end'], p['kind']))
    db().commit()
    if d.get('activate'):
        for t in q('select * from timetables where active=1'):
            if set(t['days'].split(',')) & set(d['days'].split(',')): q('update timetables set active=0 where id=?', (t['id'],))
        q('update timetables set active=1 where id=?', (tid,))
    audit(u, f"created timetable {tid} active={bool(d.get('activate'))}"); return jsonify(id=tid, warnings=warn)
@app.get('/api/timetable')
def gett():
    me(); return jsonify([dict(t, periods=q('select * from periods where tt_id=? order by start', (t['id'],))) for t in q('select * from timetables where active=1')])
def affected(day, st, en):  # periods a student misses; snapshot stored on the OD row
    wd = DT.strptime(day, '%Y-%m-%d').strftime('%a').lower()
    for t in q('select * from timetables where active=1 and effective_from<=?', (day,)):
        if wd in t['days'].split(','):
            return [p for p in q('select label,start,end from periods where tt_id=? and kind="class" order by start', (t['id'],)) if mins(p['start']) < mins(en) and mins(p['end']) > mins(st)]
    return []
@app.get('/api/impact')  # academic-impact preview while scheduling
def impact(): me(); a = request.args; return jsonify(affected(a['date'], a['start'], a['end']))

# ---------- events ----------
@app.post('/api/events')
def mkevent():
    u = me(); d = request.json; can(u, d['club_id'], 'event.edit')
    if d['date'] < str(D.today()): raise E('event date is in the past')
    q('insert into events(club_id,title,description,date,start,end,venue,capacity) values(?,?,?,?,?,?,?,?)',
      (d['club_id'], d['title'], d.get('description'), d['date'], d['start'], d['end'], d['venue'], int(d['capacity'])))
    return jsonify(ok=1)
@app.post('/api/events/<int:i>/submit')
def submit(i):
    u = me(); ev = club_of(i); can(u, ev['club_id'], 'event.edit')
    if ev['status'] not in ('draft', 'rejected'): raise E('only draft/rejected events can be submitted')
    q('update events set status="pending" where id=?', (i,))
    c = q('select coordinator_id from clubs where id=?', (ev['club_id'],), True)
    if c['coordinator_id']: notify(c['coordinator_id'], f"Event '{ev['title']}' awaits your approval")
    return jsonify(ok=1)
@app.post('/api/events/<int:i>/decide')
def decide(i):
    u = need('faculty', 'super_admin'); ev = club_of(i); d = request.json
    c = q('select * from clubs where id=?', (ev['club_id'],), True)
    if u['role'] == 'faculty' and c['coordinator_id'] != u['id']: raise E('you are not this club\'s coordinator', 403)
    if ev['status'] != 'pending': raise E('event is not pending')
    if d['approve']: q('update events set status="approved",reject_reason=null where id=?', (i,))
    else:
        if not d.get('reason'): raise E('rejection needs a reason')
        q('update events set status="rejected",reject_reason=? where id=?', (d['reason'], i))
    if c['admin_id']: notify(c['admin_id'], f"Event '{ev['title']}' {'approved' if d['approve'] else 'rejected'}")
    audit(u, f"event {i} approve={d['approve']}"); return jsonify(ok=1)
FLOW = {'approved': {'ongoing', 'cancelled'}, 'ongoing': {'completed'}}
@app.post('/api/events/<int:i>/status')
def setstatus(i):
    u = me(); ev = club_of(i); can(u, ev['club_id'], 'event.edit'); to = request.json['to']
    if to not in FLOW.get(ev['status'], ()): raise E(f"cannot move {ev['status']} -> {to}")
    q('update events set status=? where id=?', (to, i)); return jsonify(ok=1)
@app.get('/api/events')
def events():
    u = me(); base = 'select e.*,c.name club,(select count(*) from registrations r where r.event_id=e.id) registered from events e join clubs c on c.id=e.club_id'
    if u['role'] == 'student': rows = q(base + " where e.status in('approved','ongoing','completed')")
    elif u['role'] == 'faculty': rows = q(base + ' where c.coordinator_id=?', (u['id'],))
    elif u['role'] == 'club_admin': rows = q(base + ' where c.admin_id=? or e.club_id in(select club_id from club_members where user_id=?)', (u['id'], u['id']))
    else: rows = q(base)
    for r in rows: r['periods'] = affected(r['date'], r['start'], r['end'])
    return jsonify(rows)
@app.post('/api/events/<int:i>/register')
def register(i):
    u = need('student'); ev = club_of(i)
    q('insert into registrations(event_id,student_id) values(?,?)', (i, u['id']))  # trigger enforces approval + capacity
    notify(u['id'], f"Registered for {ev['title']}"); return jsonify(ok=1)
@app.get('/api/my/registrations')
def myregs(): u = need('student'); return jsonify(q('select r.id,e.title,e.date,r.attended from registrations r join events e on e.id=r.event_id where student_id=?', (u['id'],)))

# ---------- ProofOD: rotating QR check-in feeds OD + certificates ----------
def tok(i, off=0): return hmac.new(app.secret_key.encode(), f"{i}:{int(time.time() // 30) - off}".encode(), hashlib.sha256).hexdigest()[:10]
@app.get('/api/events/<int:i>/qr')
def qr(i):
    u = me(); ev = club_of(i); can(u, ev['club_id'], 'attendance.mark')
    if ev['status'] != 'ongoing': raise E('event is not ongoing')
    return jsonify(token=tok(i), valid_seconds=30)
@app.post('/api/events/<int:i>/checkin')
def checkin(i):
    u = need('student'); ev = club_of(i); t = request.json.get('token', '')
    if ev['status'] != 'ongoing': raise E('event is not ongoing')
    if not (hmac.compare_digest(t, tok(i)) or hmac.compare_digest(t, tok(i, 1))): raise E('QR expired or invalid')
    if not q('update registrations set attended=1 where event_id=? and student_id=? returning id', (i, u['id'])): raise E('you are not registered')
    return jsonify(ok=1)

# ---------- OD ----------
@app.post('/api/od')
def od():
    u = need('student'); r = q('select r.*,e.date,e.start,e.end from registrations r join events e on e.id=r.event_id where r.id=?', (request.json['reg_id'],), True)
    if not r or r['student_id'] != u['id']: raise E('OD needs your own event registration', 403)
    if not u['mentor_id']: raise E('no class mentor assigned')
    ps = affected(r['date'], r['start'], r['end'])
    q('insert into od_requests(reg_id,student_id,mentor_id,periods_snapshot) values(?,?,?,?)', (r['id'], u['id'], u['mentor_id'], json.dumps(ps)))
    notify(u['mentor_id'], f"New OD request from {u['name']} ({u['ra_number']})"); return jsonify(periods=ps)
@app.get('/api/od')
def ods():
    u = me(); col = {'student': 'o.student_id', 'faculty': 'o.mentor_id'}.get(u['role'])
    sql = '''select o.id,o.status,o.remark,o.periods_snapshot,s.name student,s.ra_number,e.title,e.date,e.start,e.end,e.venue,r.attended verified
             from od_requests o join users s on s.id=o.student_id join registrations r on r.id=o.reg_id join events e on e.id=r.event_id'''
    return jsonify(q(sql + (f' where {col}=?' if col else ''), (u['id'],) if col else ()))
@app.post('/api/od/<int:i>/decide')
def oddecide(i):
    u = need('faculty', 'super_admin'); o = q('select * from od_requests where id=?', (i,), True); d = request.json
    if not o: raise E('not found', 404)
    if u['role'] == 'faculty' and o['mentor_id'] != u['id']: raise E('not your mentee', 403)
    if o['status'] != 'pending': raise E('already decided')
    q('update od_requests set status=?,remark=? where id=?', ('approved' if d['approve'] else 'rejected', d.get('remark'), i))
    notify(o['student_id'], f"Your OD was {'approved' if d['approve'] else 'rejected'}"); return jsonify(ok=1)

# ---------- certificates ----------
@app.post('/api/events/<int:i>/certs')
def certs(i):
    u = me(); ev = club_of(i); can(u, ev['club_id'], 'cert.issue')
    if ev['status'] != 'completed': raise E('event must be completed')
    n = 0
    for r in q('select r.id,r.student_id from registrations r where event_id=? and attended=1 and id not in(select reg_id from certificates)', (i,)):
        q('insert into certificates(code,reg_id,label,issued_by) values(?,?,?,?)', ('CS-' + secrets.token_hex(5).upper(), r['id'], request.json.get('label', 'Participant'), u['id']))
        notify(r['student_id'], f"Certificate issued for {ev['title']}"); n += 1
    return jsonify(issued=n)
def certrow(code): return q('''select c.code,c.label,c.issued,s.name,s.ra_number,e.title,e.date,cl.name club from certificates c join registrations r on r.id=c.reg_id
    join users s on s.id=r.student_id join events e on e.id=r.event_id join clubs cl on cl.id=e.club_id where c.code=?''', (code,), True)
@app.get('/api/verify/<code>')
def verify(code): c = certrow(code); return (jsonify(valid=True, **c) if c else (jsonify(valid=False), 404))
@app.get('/api/my/certs')
def mycerts(): u = need('student'); return jsonify(q('select c.code,c.label,e.title from certificates c join registrations r on r.id=c.reg_id join events e on e.id=r.event_id where r.student_id=?', (u['id'],)))
@app.get('/cert/<code>')
def certpage(code):
    c = certrow(code)
    if not c: raise E('invalid certificate', 404)
    return f"<body style='font:20px Georgia;text-align:center;padding:60px;border:8px double #123'><h1>{c['club']}</h1><p>certifies that</p><h2>{c['name']} ({c['ra_number']})</h2><p>took part as <b>{c['label']}</b> in <b>{c['title']}</b> on {c['date']}</p><small>Certificate {c['code']} - verify at /api/verify/{c['code']} - print to save as PDF</small></body>"

# ---------- notifications & analytics ----------
@app.get('/api/notifications')
def notifs(): u = me(); return jsonify(q('select * from notifications where user_id=? order by id desc limit 30', (u['id'],)))
@app.get('/api/stats')
def stats():
    need('super_admin', 'admin')
    return jsonify(clubs=q('''select c.name,(select count(*) from club_members m where m.club_id=c.id) members,
      (select count(*) from events e where e.club_id=c.id and e.status='completed') events_held,
      (select round(avg(x.n),1) from (select sum(r.attended) n from registrations r join events e on e.id=r.event_id where e.club_id=c.id group by e.id) x) avg_attendance from clubs c'''),
      pending_events=q("select id,title from events where status='pending'"))

# ---------- badges ----------
@app.post('/api/clubs/<int:cid>/badges')
def mkbadge(cid):
    u = me(); can(u, cid, 'cert.issue'); q('insert into badges(club_id,name) values(?,?)', (cid, request.json['name'])); return jsonify(ok=1)
@app.post('/api/badges/<int:bid>/award')
def award(bid):
    u = me(); b = q('select * from badges where id=?', (bid,), True)
    if not b: raise E('no such badge', 404)
    can(u, b['club_id'], 'cert.issue'); s = q('select id from users where ra_number=?', (request.json['ra_number'].upper(),), True)
    if not s: raise E('unknown RA Number', 404)
    q('insert into user_badges(badge_id,user_id,awarded_by) values(?,?,?)', (bid, s['id'], u['id'])); notify(s['id'], f"You earned the badge '{b['name']}'"); return jsonify(ok=1)
@app.get('/api/my/badges')
def mybadges(): u = need('student'); return jsonify(q('select b.name,c.name club from user_badges ub join badges b on b.id=ub.badge_id join clubs c on c.id=b.club_id where ub.user_id=?', (u['id'],)))

# ---------- context-linked messaging (faculty <-> faculty / club admin) ----------
@app.post('/api/messages')
def msg():
    u = need('faculty', 'club_admin', 'super_admin', 'admin'); d = request.json
    r = q('select * from users where email=?', (d['to_email'].lower(),), True)
    if not r or r['role'] == 'student': raise E('recipient must be staff')
    if 'faculty' not in (u['role'], r['role']) and 'super_admin' not in (u['role'], r['role']): raise E('one side must be faculty', 403)
    q('insert into messages(sender_id,recipient_id,ctx_type,ctx_id,body) values(?,?,?,?,?)', (u['id'], r['id'], d.get('ctx_type', 'general'), d.get('ctx_id'), d['body']))
    notify(r['id'], f"New message from {u['name']}"); return jsonify(ok=1)
@app.get('/api/messages')
def inbox():
    u = me(); return jsonify(q('select m.ctx_type,m.ctx_id,m.body,m.at,s.name sender from messages m join users s on s.id=m.sender_id where recipient_id=? or sender_id=? order by m.id desc limit 30', (u['id'], u['id'])))

# ---------- misc admin ----------
@app.get('/api/users')
def users(): need('super_admin', 'admin'); return jsonify(q('select id,name,email,role,ra_number from users'))
@app.post('/api/clubs/<int:cid>/archive')
def archive(cid): u = need('super_admin', 'admin'); q('update clubs set status="archived" where id=?', (cid,)); audit(u, f'archived club {cid}'); return jsonify(ok=1)

# ---------- Google Sign-In (students): set GOOGLE_CLIENT_ID in .env ----------
@app.get('/api/config')
def cfg(): return jsonify(google_client_id=os.environ.get('GOOGLE_CLIENT_ID', ''))
@app.post('/api/google')
def google():
    import urllib.request, urllib.parse
    cid = os.environ.get('GOOGLE_CLIENT_ID')
    if not cid: raise E('Google Sign-In is not configured')
    try: info = json.load(urllib.request.urlopen('https://oauth2.googleapis.com/tokeninfo?id_token=' + urllib.parse.quote(request.json['id_token']), timeout=8))
    except Exception: raise E('invalid Google token', 401)
    if info.get('aud') != cid or info.get('email_verified') != 'true': raise E('Google token rejected', 401)
    u = q('select * from users where email=? and role="student"', (info['email'].lower(),), True)
    if not u: raise E('No student with this email. Sign up once with your RA Number first.', 404)
    session['uid'] = u['id']; return jsonify(id=u['id'], name=u['name'], role=u['role'])

if __name__ == '__main__': app.run(debug=False, port=5000)
