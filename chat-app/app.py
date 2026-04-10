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
socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# ================= DATABASE =================

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

# ================= MEMORY =================

online_users = {}

# ================= ROUTES =================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)
    return file.filename

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json

    name = data['name']
    password = data['password']

    exist = Room.query.filter_by(name=name, password=password).first()
    if exist:
        return {"status": "error", "msg": "الغرفة موجودة بنفس الاسم والباسورد"}

    db.session.add(Room(name=name, password=password))
    db.session.commit()

    return {"status": "ok", "msg": "تم إنشاء الغرفة"}

# ================= SOCKET =================

@socketio.on('join')
def join(data):
    room = data['room']
    password = data['password']
    username = data['username']
    sid = request.sid

    # تحقق من الغرفة
    r = Room.query.filter_by(name=room, password=password).first()
    if not r:
        print(f"❌ Failed login: {room}")
        return

    join_room(room)

    # ================= IP DETECTION =================
    ip = request.headers.get('X-Forwarded-For')

    if ip:
        ip = ip.split(',')[0]
    else:
        ip = request.remote_addr

    try:
        geo = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city").json()
        country = geo.get("country", "Unknown")
        city = geo.get("city", "Unknown")

        print(f"🌍 {username} joined [{room}] from {country} - {city} (IP: {ip})")

    except Exception as e:
        print(f"⚠️ IP lookup failed: {e}")

    # ================= USERS =================
    if room not in online_users:
        online_users[room] = {}

    online_users[room][sid] = username

    # إرسال الرسائل القديمة
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
    room = data['room']

    msg = Message(
        room=room,
        username=data.get('username'),
        content=data.get('msg'),
        file=data.get('file')
    )

    db.session.add(msg)
    db.session.commit()

    socketio.emit('message', data, to=room)

def emit_users(room):
    users = list(online_users.get(room, {}).values())
    socketio.emit('users', users, to=room)

@socketio.on('disconnect')
def disconnect():
    sid = request.sid

    for room in list(online_users.keys()):
        if sid in online_users[room]:
            username = online_users[room].pop(sid)

            print(f"🔴 {username} left [{room}]")

            emit_users(room)

# ================= RUN =================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    socketio.run(app, host='0.0.0.0', port=10000)
