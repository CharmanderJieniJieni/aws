from app import webapp
from flask import redirect, render_template, request, g, url_for, session
from wand.image import Image

import tempfile
import os
import boto3
import uuid
import mysql.connector
import base64

from app.config import db_config



def connect_to_database():
    return mysql.connector.connect(user=db_config['user'],
                                   password=db_config['password'],
                                   host=db_config['host'],
                                   database=db_config['database'])


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = connect_to_database()
    return db


@webapp.teardown_appcontext
def teardown_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


@webapp.route('/', methods=['GET'])
def main():
    if 'user_id' in session:
        return render_template("landing.html")
    else:
        return render_template("main.html")


@webapp.route('/register', methods=['GET'])
def register():
    session.clear()
    return render_template("register.html")


@webapp.route('/register_submit', methods=['POST'])
def register_submit():
    username = request.form.get('username', "")
    password = request.form.get('password', "")
    pwConfirm= request.form.get('pwconfirm', "")
    
    error = False

    if password!=pwConfirm:
        error = True
        error_msg="Error: Password mismatch!"
    
    if password=="":
        error = True
        error_msg="Error: Password cannot be empty"
    
    if username=="":
        error = True
        error_msg="Error: Username cannot be empty"
    
    if error==False:
        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''Select * from users where login=%s'''
        cursor.execute(query, (username,))
        number=cursor.rowcount
        if number>0:
            error = True
            error_msg="Error: Username already exits"
        else:
            cnx = get_db()
            cursor = cnx.cursor(buffered=True)
            query = '''INSERT INTO users (login, password) VALUES (%s,%s)'''
            cursor.execute(query, (username,password))
            cnx.commit()   
    
    if error==True:
        return render_template("register.html",error_msg=error_msg)    
    else:
        return render_template("register.html",error_msg="Register Successful!")

@webapp.route('/login', methods=['GET'])
def login():
    if 'user_id' in session:
        return render_template("landing.html")
    else:
        return render_template("login.html")

@webapp.route('/logout', methods=['GET'])
def logout():
    return render_template("logout.html")

@webapp.route('/logout_submit', methods=['POST'])
def logout_submit():
    session.clear()
    return render_template("login.html")

@webapp.route('/login_submit', methods=['POST'])
def login_submit():
    username = request.form.get('username', "")
    password = request.form.get('password', "")
    error = False
    if password=="":
        error = True
        error_msg="Error: Password cannot be empty"
    
    if username=="":
        error = True
        error_msg="Error: Username cannot be empty"
   
    if error==False:
        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''Select * from users where login=%s and password=%s'''
        cursor.execute(query, (username, password))
        number=cursor.rowcount      
        if number==0:
            error=True
            error_msg="Username or password incorrect"
        else:
            row = cursor.fetchone()
            user_id = row[0]
            session['user_id']=user_id
    
    if error==True:
        return render_template("login.html",error_msg=error_msg) 
    else:
        return render_template("landing.html")    

@webapp.route('/landing', methods=['GET'])
def landing():
    if 'user_id' in session:
        return render_template("landing.html")
    else:
        return render_template("login.html")

@webapp.route('/gallary', methods=['GET'])
def gallary():
    if 'user_id' not in session:
        return render_template("login.html")
    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    user_id=str(session['user_id'])
    #print(user_id)
    query = '''select id,key1 from images where userId= %s'''
    cursor.execute(query, (user_id, ))
    b64List=[]
    formatList=[]
    idList=[]
    count=0
    countList=[]
    for row in cursor:
        s3 = boto3.client('s3')
        with open('image_filename','wb') as data:
            s3.download_fileobj('ece1779images',row[1],data)
        with open('image_filename', 'rb') as dataRead:
            encoded_string = base64.b64encode(dataRead.read()).decode("utf-8")
        form=row[1].split('.')[-1]
        b64List.append(encoded_string)
        formatList.append(form)
        idList.append(row[0])
        countList.append(count)
        count+=1
        #print(encoded_string )
    return render_template("gallary.html", b64List=b64List, formatList=formatList, idList=idList, countList=countList)

@webapp.route('/detail/<int:id>',methods=['GET'])
def detail(id):
    if 'user_id' not in session:
        return render_template("login.html") 
    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    #print(user_id)
    query = '''select key1,key2,key3,key4 from images where id= %s'''
    cursor.execute(query, (id, ))
    row = cursor.fetchone()
    s3 = boto3.client('s3')
    b64List=[]
    formatList=[]
    countList=[]
    count=0
    descrip=["original", "liquid resize", "sinusoid colour enhancement", "vertical flip with gamma colour enhancement"]
    for count in range(0,4):
        with open('image_filename','wb') as data:
            s3.download_fileobj('ece1779images',row[count],data)
        with open('image_filename', 'rb') as dataRead:
            encoded_string = base64.b64encode(dataRead.read()).decode("utf-8")
        form=row[1].split('.')[-1]
        b64List.append(encoded_string)
        formatList.append(form)
        countList.append(count)
        count+=1
        #print(encoded_string )
    return render_template("detail.html", b64List=b64List, countList=countList,formatList=formatList,descrip=descrip)


@webapp.route('/test/FileUpload', methods=['POST', 'GET'])
def file_upload():
    if request.method == 'GET':
        return render_template("upload.html", authenticated='user_id' in session)

    # check if the post request has the file part
    if 'uploadedfile' not in request.files:
        return redirect(url_for('main'))

    new_file = request.files['uploadedfile']

    tempdir = tempfile.gettempdir()
    fname = os.path.join(tempdir, new_file.filename)
    new_file.save(fname)

    # if user does not select file, browser also
    # submit a empty part without filename
    if new_file.filename == '':
        return redirect(url_for('main'))

    s3 = boto3.client('s3')

    key1 = str(uuid.uuid4()) + '.' + new_file.filename.split('.')[-1]
    s3.upload_fileobj(open(fname, 'rb'), "ece1779images", key1)

    img = Image(filename=fname)

    i = img.clone()
    i.liquid_rescale(100, 100)
    fname_resized = os.path.join(tempdir, 'resized_' + new_file.filename)
    i.save(filename=fname_resized)
    key2 = str(uuid.uuid4()) + '.' + new_file.filename.split('.')[-1]
    s3.upload_fileobj(open(fname_resized, 'rb'), "ece1779images", key2)

    i = img.clone()
    frequency = 3
    phase_shift = -90
    amplitude = 0.2
    bias = 0.7
    i.function('sinusoid', [frequency, phase_shift, amplitude, bias])
    fname_sinusoid = os.path.join(tempdir, 'rotated_' + new_file.filename)
    i.save(filename=fname_sinusoid)
    key3 = str(uuid.uuid4()) + '.' + new_file.filename.split('.')[-1]
    s3.upload_fileobj(open(fname_sinusoid, 'rb'), "ece1779images", key3)

    i = img.clone()
    i.flip()
    i.gamma(1.5)
    fname_flipped = os.path.join(tempdir, 'flipped_' + new_file.filename)
    i.save(filename=fname_flipped)
    key4 = str(uuid.uuid4()) + '.' + new_file.filename.split('.')[-1]
    s3.upload_fileobj(open(fname_flipped, 'rb'), "ece1779images", key4)

    cnx = get_db()

    if 'user_id' in session:
        user_id = session['user_id']
    else:
        cursor = cnx.cursor(buffered=True)
        username = request.form.get('userID', "")
        password = request.form.get('password', "")
        query = '''SELECT * FROM users WHERE login=%s and password=%s'''
        cursor.execute(query, (username, password))
        number = cursor.rowcount
        if number > 0:
            row = cursor.fetchone()
            user_id = row[0]
            session['user_id'] = user_id
        else:
            return redirect(url_for('main'))

    cursor = cnx.cursor()
    query = '''INSERT INTO images (userId, key1, key2, key3, key4) VALUES (%s,%s,%s,%s,%s)'''
    cursor.execute(query, (user_id, key1, key2, key3, key4))  # TODO: get userId from session
    cnx.commit()
    return redirect(url_for('gallary'))

webapp.secret_key = b"h\xbc\xc4\x05\xcb\xd8b\x98+'\xe9m\xdbY\xc6C\x0f\x12\x01\x86\x05\xc42\x9b"
