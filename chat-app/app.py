from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
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

class UserStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    room = db.Column(db.String(50))
    last_seen = db.Column(db.String(50))
    online = db.Column(db.Boolean, default=False)

# ================= MEMORY =================

online_users = {}  # room -> {sid: username}

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

    r = Room.query.filter_by(name=room, password=password).first()
    if not r:
        return

    join_room(room)

    # تسجيل المستخدم
    if room not in online_users:
        online_users[room] = {}

    online_users[room][sid] = username

    # تحديث الحالة
    status = UserStatus.query.filter_by(username=username, room=room).first()

    if not status:
        status = UserStatus(username=username, room=room)

    status.online = True
    status.last_seen = "Online"

    db.session.add(status)
    db.session.commit()

    # إرسال الرسائل القديمة
    messages = Message.query.filter_by(room=room).all()

    for msg in messages:
        socketio.emit('message', {
            'username': msg.username,
            'msg': msg.content,
            'file': msg.file
        }, to=sid)

    # تحديث قائمة المستخدمين
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
    users = []

    for sid, username in online_users.get(room, {}).items():
        users.append(username)

    socketio.emit('users', users, to=room)

@socketio.on('disconnect')
def disconnect():
    sid = request.sid

    for room in list(online_users.keys()):
        if sid in online_users[room]:

            username = online_users[room].pop(sid)

            # تحديث آخر ظهور
            status = UserStatus.query.filter_by(username=username, room=room).first()
            if status:
                status.online = False
                status.last_seen = datetime.now().strftime("%Y-%m-%d %H:%M")
                db.session.commit()

            emit_users(room)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)