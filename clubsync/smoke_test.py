import os; os.environ['DB_PATH']='test.db'
import subprocess; subprocess.run(['python3','seed.py'],check=True,capture_output=True)
from app import app
from datetime import date, timedelta
day=str(date.today()+timedelta(days=(7-date.today().weekday())%7 or 7))  # next Monday
def cl(e):
    c=app.test_client(); r=c.post('/api/login',json={'email':e,'password':'demo123'}); assert r.status_code==200; return c
def chk(name,r,code):
    ok=r.status_code==code; print(('PASS' if ok else 'FAIL'),name,r.status_code,r.json if not ok else ''); assert ok
su,ca,fa,vol,st=cl('super@demo.in'),cl('club@demo.in'),cl('faculty@demo.in'),cl('vol@demo.in'),cl('stu@demo.in')
ev=dict(club_id=1,title='HackNight',date=day,start='10:30',end='13:00',venue='Lab',capacity=1)
chk('club admin cannot edit timetable',ca.post('/api/timetable',json={}),403)
chk('overlap rejected',su.post('/api/timetable',json=dict(name='x',days='sat',effective_from=day,periods=[dict(label='a',start='09:00',end='10:00',kind='class'),dict(label='b',start='09:30',end='10:30',kind='class')])),400)
chk('create event',ca.post('/api/events',json=ev),200)
chk('register draft blocked (trigger)',st.post('/api/events/1/register'),409)
chk('student cannot approve',st.post('/api/events/1/decide',json={'approve':True}),403)
chk('submit',vol.post('/api/events/1/submit'),200)
chk('faculty rejects',fa.post('/api/events/1/decide',json={'approve':False,'reason':'clash'}),200)
chk('rejected not listed for students',st.get('/api/events'),200); assert st.get('/api/events').json==[]
chk('resubmit',ca.post('/api/events/1/submit'),200); chk('approve',fa.post('/api/events/1/decide',json={'approve':True}),200)
chk('student registers',st.post('/api/events/1/register'),200)
chk('overbooking blocked',vol.post('/api/events/1/register'),409)
chk('duplicate blocked',st.post('/api/events/1/register'),409)
r=st.post('/api/od',json={'reg_id':1}); chk('OD raised',r,200); print('  periods:',[p['label'] for p in r.json['periods']])
chk('student cannot self-approve OD',st.post('/api/od/1/decide',json={'approve':True}),403)
chk('mentor approves',fa.post('/api/od/1/decide',json={'approve':True}),200)
ca.post('/api/events/1/status',json={'to':'ongoing'}); t=ca.get('/api/events/1/qr').json['token']
chk('bad QR',st.post('/api/events/1/checkin',json={'token':'nope'}),400); chk('QR check-in',st.post('/api/events/1/checkin',json={'token':t}),200)
ca.post('/api/events/1/status',json={'to':'completed'}); r=ca.post('/api/events/1/certs',json={}); chk('certs',r,200); print('  issued',r.json)
code=st.get('/api/my/certs').json[0]['code']; chk('verify',app.test_client().get('/api/verify/'+code),200)
chk('create badge',ca.post('/api/clubs/1/badges',json={'name':'First Event'}),200)
chk('vol cannot award (no perm)',vol.post('/api/badges/1/award',json={'ra_number':'RA2211003010001'}),403)
chk('award badge',ca.post('/api/badges/1/award',json={'ra_number':'RA2211003010001'}),200)
chk('student sees badge',st.get('/api/my/badges'),200); assert len(st.get('/api/my/badges').json)==1
chk('message in OD context',fa.post('/api/messages',json={'to_email':'club@demo.in','ctx_type':'event','ctx_id':1,'body':'Please share the venue plan'}),200)
chk('student cannot message',st.post('/api/messages',json={'to_email':'club@demo.in','body':'hi'}),403)
chk('admin dashboard',cl('admin@demo.in').get('/api/stats'),200); chk('student blocked from stats',st.get('/api/stats'),403)
