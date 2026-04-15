from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# ===== DATABASE =====

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

# ===== MEMORY =====
online_users = {}

# ===== ROUTES =====

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    name = data['name']
    password = data['password']

    exist = Room.query.filter_by(name=name).first()
    if exist:
        return {"msg": "اسم الغرفة مستخدم"}

    db.session.add(Room(name=name, password=password))
    db.session.commit()
    return {"msg": "تم إنشاء الغرفة"}

# ===== 🚀 CHUNK UPLOAD =====

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    chunk = request.files['chunk']
    filename = request.form['filename']
    chunk_index = int(request.form['index'])

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    mode = 'ab' if chunk_index > 0 else 'wb'
    with open(filepath, mode) as f:
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
        return

    join_room(room)

    if room not in online_users:
        online_users[room] = {}

    online_users[room][request.sid] = username

    # إرسال الرسائل القديمة
    msgs = Message.query.filter_by(room=room).all()
    for m in msgs:
        socketio.emit('message', {
            "username": m.username,
            "msg": m.content,
            "file": m.file
        }, to=request.sid)

    emit_users(room)

@socketio.on('message')
def message(data):
    db.session.add(Message(
        room=data['room'],
        username=data['username'],
        content=data.get('msg'),
        file=data.get('file')
    ))
    db.session.commit()

    socketio.emit('message', data, to=data['room'])

# 🔥 إشعار الرفع
@socketio.on('uploading')
def uploading(data):
    socketio.emit('uploading', data, to=data['room'])

@socketio.on('disconnect')
def disconnect():
    sid = request.sid
    for room in online_users:
        if sid in online_users[room]:
            online_users[room].pop(sid)
            emit_users(room)

def emit_users(room):
    users = list(online_users.get(room, {}).values())
    socketio.emit('users', users, to=room)

# ===== RUN =====

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    socketio.run(app, host='0.0.0.0', port=10000)
