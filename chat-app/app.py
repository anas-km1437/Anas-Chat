from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# ===== CONFIG =====
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret!')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 🔥 مهم: async_mode
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# إنشاء مجلد الرفع
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ===== DATABASE =====

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    content = db.Column(db.String(500))
    file = db.Column(db.String(200))
    time = db.Column(db.String(50))  # 🆕 وقت الرسالة

# ===== ONLINE USERS =====
online_users = {}

# ===== ROUTES =====

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    name = data.get('name')
    password = data.get('password')

    exist = Room.query.filter_by(name=name).first()
    if exist:
        return {"msg": "اسم الغرفة مستخدم"}, 400

    db.session.add(Room(name=name, password=password))
    db.session.commit()

    return {"msg": "تم إنشاء الغرفة"}

# ===== 🚀 UPLOAD CHUNK =====

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    chunk = request.files['chunk']
    filename = request.form['filename']
    index = int(request.form['index'])

    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    mode = 'ab' if index > 0 else 'wb'
    with open(path, mode) as f:
        f.write(chunk.read())

    return "ok"

# ===== SOCKET =====

@socketio.on('join')
def join(data):
    room = data['room']
    username = data['username']
    password = data['password']

    r = Room.query.filter_by(name=room, password=password).first()
    if not r:
        emit("error", {"msg": "كلمة السر غلط"})
        return

    join_room(room)

    if room not in online_users:
        online_users[room] = {}

    online_users[room][request.sid] = username

    # 🆕 إرسال الرسائل القديمة
    msgs = Message.query.filter_by(room=room).all()
    for m in msgs:
        emit('message', {
            "username": m.username,
            "msg": m.content,
            "file": m.file,
            "time": m.time
        })

    emit_users(room)

@socketio.on('message')
def message(data):
    from datetime import datetime

    time_now = datetime.now().strftime("%H:%M")

    db.session.add(Message(
        room=data['room'],
        username=data['username'],
        content=data.get('msg'),
        file=data.get('file'),
        time=time_now
    ))
    db.session.commit()

    data['time'] = time_now

    socketio.emit('message', data, to=data['room'])

# 🔥 typing
@socketio.on('typing')
def typing(data):
    emit('typing', data, to=data['room'], include_self=False)

# 🔥 uploading
@socketio.on('uploading')
def uploading(data):
    emit('uploading', data, to=data['room'], include_self=False)

@socketio.on('disconnect')
def disconnect():
    sid = request.sid

    for room in list(online_users.keys()):
        if sid in online_users[room]:
            online_users[room].pop(sid)
            emit_users(room)
            break

def emit_users(room):
    users = list(online_users.get(room, {}).values())
    socketio.emit('users', users, to=room)

# ===== RUN =====

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
