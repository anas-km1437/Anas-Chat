from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room
from flask_sqlalchemy import SQLAlchemy
import requests
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'

db = SQLAlchemy(app)
# تأكد من أن cors_allowed_origins="*" للسماح بالاتصال من أي مكان عند الرفع على Render
socketio = SocketIO(app, cors_allowed_origins="*")

# التأكد من وجود مجلد الرفع
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# ================= DATABASE MODELS =================

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    content = db.Column(db.String(500))
    file = db.Column(db.String(200))

# ================= ONLINE MEMORY =================

online_users = {} # { "room_name": { "sid": "username" } }

# ================= HTTP ROUTES =================

@app.route('/')
def landing():
    """عرض صفحة الهبوط التعريفية"""
    return render_template('landing.html')

@app.route('/chat')
def chat():
    """عرض صفحة الدردشة الفعلية"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return "No file", 400
    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)
    return file.filename

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    name = data.get('name')
    password = data.get('password')

    exist = Room.query.filter_by(name=name).first()
    if exist:
        return {"status": "error", "msg": "عذراً، اسم الغرفة مأخوذ مسبقاً!"}

    new_room = Room(name=name, password=password)
    db.session.add(new_room)
    db.session.commit()
    return {"status": "ok", "msg": "تم إنشاء الغرفة بنجاح! يمكنك الدخول الآن."}

# ================= SOCKET.IO EVENTS =================

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    password = data.get('password')
    username = data.get('username')
    sid = request.sid

    # التحقق من وجود الغرفة وصحة كلمة السر
    r = Room.query.filter_by(name=room, password=password).first()
    if not r:
        print(f"❌ محاولة دخول خاطئة للغرفة: {room}")
        return

    join_room(room)

    # تحديد الموقع الجغرافي (اختياري)
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    try:
        geo = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city", timeout=5).json()
        print(f"🌍 {username} دخل [{room}] من {geo.get('country')} (IP: {ip})")
    except:
        print(f"🌍 {username} دخل [{room}] (IP: {ip})")

    # إدارة المستخدمين المتصلين
    if room not in online_users:
        online_users[room] = {}
    online_users[room][sid] = username

    # إرسال تاريخ الرسائل للمستخدم الجديد فقط
    messages = Message.query.filter_by(room=room).all()
    for msg in messages:
        socketio.emit('message', {
            'username': msg.username,
            'msg': msg.content,
            'file': msg.file
        }, to=sid)

    emit_users(room)

@socketio.on('message')
def handle_message(data):
    room = data.get('room')
    username = data.get('username')
    content = data.get('msg')
    file_name = data.get('file')

    # حفظ الرسالة في قاعدة البيانات
    new_msg = Message(room=room, username=username, content=content, file=file_name)
    db.session.add(new_msg)
    db.session.commit()

    # بث الرسالة للجميع في الغرفة
    socketio.emit('message', data, to=room)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    for room, users in online_users.items():
        if sid in users:
            username = users.pop(sid)
            print(f"🔴 {username} غادر الغرفة [{room}]")
            emit_users(room)
            break

def emit_users(room):
    """تحديث قائمة المستخدمين المتصلين عند الجميع"""
    users = list(online_users.get(room, {}).values())
    socketio.emit('users', users, to=room)

# ================= RUN APP =================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # port 10000 هو الافتراضي لـ Render
    socketio.run(app, host='0.0.0.0', port=10000)
