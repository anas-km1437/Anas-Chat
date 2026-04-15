from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'

db = SQLAlchemy(app)

# ⚡ أسرع إعداد
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ===== DB =====

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


online_users = {}

# ===== ROUTES =====

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json

    if Room.query.filter_by(name=data['name']).first():
        return {"msg": "الغرفة موجودة"}

    db.session.add(Room(name=data['name'], password=data['password']))
    db.session.commit()

    return {"msg": "تم إنشاء الغرفة ⚡"}


# ===== UPLOAD (FAST) =====

@app.route('/upload', methods=['POST'])
def upload():
    file = request.files['file']
    path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(path)
    return file.filename


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

    online_users.setdefault(room, {})
    online_users[room][request.sid] = username

    # إرسال الرسائل القديمة
    for m in Message.query.filter_by(room=room).all():
        emit('message', {
            "username": m.username,
            "msg": m.content,
            "file": m.file
        })

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

    emit('message', data, to=data['room'])


@socketio.on('typing')
def typing(data):
    emit('typing', data, to=data['room'])


@socketio.on('disconnect')
def disconnect():
    sid = request.sid

    for room in list(online_users.keys()):
        if sid in online_users[room]:
            online_users[room].pop(sid)
            emit_users(room)


def emit_users(room):
    emit('users', list(online_users.get(room, {}).values()), to=room)


# ===== RUN =====

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    socketio.run(app, host='0.0.0.0', port=10000)
