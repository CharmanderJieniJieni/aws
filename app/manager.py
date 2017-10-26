from flask import render_template, redirect, url_for, request,g, session
from app import webapp

import boto3
from app import config
from datetime import datetime, timedelta
from operator import itemgetter
import mysql.connector
import re
import subprocess
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


@webapp.route('/manager',methods=['GET'])
# Display an HTML list of all ec2 instances
def ec2_list():
    if 'user_id' not in session:
        return render_template("login.html")
    # create connection to ec2
    ec2 = boto3.resource('ec2')

#    instances = ec2.instances.filter(
#        Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])

    instances = ec2.instances.all()
    CPU_list=[]
    CPU_index=0
    for instance in instances:
        #id=myInstance.id
 
        id= instance.id
        instance = ec2.Instance(id)
        client = boto3.client('cloudwatch')
        namespace = 'AWS/EC2'
        statistic = 'Average'                   # could be Sum,Maximum,Minimum,SampleCount,Average
        metric_name = 'CPUUtilization'
        cpu = client.get_metric_statistics(
            Period=1 * 60,
            StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
            EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
            MetricName=metric_name,
            Namespace=namespace,  # Unit='Percent',
            Statistics=[statistic],
            Dimensions=[{'Name': 'InstanceId', 'Value': id}]
        )      
        cpu_stats = []
        for point in cpu['Datapoints']:
            hour = point['Timestamp'].hour
            minute = point['Timestamp'].minute
            time = hour + minute/60
            cpu_stats.append([time,point['Average']])
        cpu_stats = sorted(cpu_stats, key=itemgetter(0))
        #print(cpu_stats[-1][1])
        if instance.instance_type != "t2.micro":
            if len(cpu_stats) > 0:
                CPU_list.append(cpu_stats[-1][1])
            else:
                CPU_list.append("Initializing")
        #   cpu_util=cpu_stats[-1][1]
        #CPU_index+=1
        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''Select * from policy'''
        cursor.execute(query)
        if cursor.rowcount > 0:
            row = cursor.fetchone()
            growCPU=row[0]
            shrinkCPU=row[1]
            ratExp=row[2]
            ratShrink=row[3]
            status=row[4]
            if status==0:
                stat="Stopped"
            else: 
               stat="Running"
    return render_template("manager/list.html",title="EC2 Instances",CPU_list=CPU_list,instances=instances,growCPU=growCPU,shrinkCPU=shrinkCPU,ratExp=ratExp,ratShrink=ratShrink,status=stat)


@webapp.route('/manager/<id>',methods=['GET'])
#Display details about a specific instance.
def ec2_view(id):
    if 'user_id' not in session:
        return render_template("login.html")
    ec2 = boto3.resource('ec2')

    instance = ec2.Instance(id)

    client = boto3.client('cloudwatch')

    metric_name = 'CPUUtilization'

    ##    CPUUtilization, NetworkIn, NetworkOut, NetworkPacketsIn,
    #    NetworkPacketsOut, DiskWriteBytes, DiskReadBytes, DiskWriteOps,
    #    DiskReadOps, CPUCreditBalance, CPUCreditUsage, StatusCheckFailed,
    #    StatusCheckFailed_Instance, StatusCheckFailed_System


    namespace = 'AWS/EC2'
    statistic = 'Average'                   # could be Sum,Maximum,Minimum,SampleCount,Average



    cpu = client.get_metric_statistics(
        Period=1 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName=metric_name,
        Namespace=namespace,  # Unit='Percent',
        Statistics=[statistic],
        Dimensions=[{'Name': 'InstanceId', 'Value': id}]
    )

    cpu_stats = []

    for point in cpu['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute/60
        cpu_stats.append([time,point['Average']])

    cpu_stats = sorted(cpu_stats, key=itemgetter(0))

    statistic = 'Sum'  # could be Sum,Maximum,Minimum,SampleCount,Average

    network_in = client.get_metric_statistics(
        Period=1 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName='NetworkIn',
        Namespace=namespace,  # Unit='Percent',
        Statistics=[statistic],
        Dimensions=[{'Name': 'InstanceId', 'Value': id}]
    )

    net_in_stats = []

    for point in network_in['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute/60
        net_in_stats.append([time,point['Sum']])

    net_in_stats = sorted(net_in_stats, key=itemgetter(0))

    network_out = client.get_metric_statistics(
        Period=5 * 60,
        StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
        EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
        MetricName='NetworkOut',
        Namespace=namespace,  # Unit='Percent',
        Statistics=[statistic],
        Dimensions=[{'Name': 'InstanceId', 'Value': id}]
    )

    net_out_stats = []

    for point in network_out['Datapoints']:
        hour = point['Timestamp'].hour
        minute = point['Timestamp'].minute
        time = hour + minute/60
        net_out_stats.append([time,point['Sum']])

        net_out_stats = sorted(net_out_stats, key=itemgetter(0))

    return render_template("manager/view.html",title="Instance Info",
                           instance=instance,
                           cpu_stats=cpu_stats,
                           net_in_stats=net_in_stats,
                           net_out_stats=net_out_stats)


@webapp.route('/manager/create',methods=['POST'])
# Start a new EC2 instance
def ec2_create():
    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    query = '''Select ami from policy'''
    cursor.execute(query)
    if cursor.rowcount > 0:
        row = cursor.fetchone()
        ami = row[0]
    else:
        return redirect(url_for('ec2_list'))

    ec2 = boto3.resource('ec2')

    instances = ec2.create_instances(ImageId=ami,
                         MinCount=1, MaxCount=1,
                         KeyName='ece1779',
                         InstanceType='t2.small',
                         Monitoring={
                             'Enabled': True
                         },
                         SubnetId=config.subnet_id)

    elb = boto3.client('elb')

    elb.register_instances_with_load_balancer(
        LoadBalancerName='ece1779',
        Instances=[
            {
                'InstanceId': instances[0].id
            },
        ])

    return redirect(url_for('ec2_list'))


@webapp.route('/manager/delete/<id>',methods=['POST'])
# Terminate a EC2 instance
def ec2_destroy(id):
    # create connection to ec2
    ec2 = boto3.resource('ec2')

    ec2.instances.filter(InstanceIds=[id]).terminate()

    return redirect(url_for('ec2_list'))

@webapp.route('/manager/autoScale',methods=['POST'])
# Start a new EC2 instance
def ec2_autoScale():
    error = False
    threshExpand = request.form.get('threshExpand', "")            
    threShrink = request.form.get('threShrink', "")
    ratioExpand = request.form.get('ratioExpand', "")
    ratioShrink = request.form.get('ratioShrink', "")
    pattern=re.compile("^0*(?:[1-9][0-9]?|100)$")
    pattern=re.compile("^0*(?:[1-9][0-9]?|100)$")
    pattern=re.compile("^0*(?:[1-9][0-9]?|100)$")
    pattern=re.compile("^0*(?:[1-9][0-9]?|100)$")
    #patternRatio=re.compile('[0-9]')
    if pattern.match(threshExpand) is not None and pattern.match(threShrink) is not None and pattern.match(ratioExpand) is not None and pattern.match(ratioShrink) is not None:
        error=False
        #error_msg="Threshold not valid"
        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''update policy set growing_threshold=%s, shrinking_threshold=%s, grow_ratio=%s, shrink_ratio=%s, running=%s'''
        cursor.execute(query,(threshExpand,threShrink,ratioExpand,ratioShrink,1))   
        cnx.commit()  
    else :
        error=True
        error_msg="Input not valid"
  
    ec2 = boto3.resource('ec2')

    instances = ec2.instances.all()
    CPU_list=[]
    CPU_index=0
    for instance in instances:
        #id=myInstance.id
 
        id= instance.id
        instance = ec2.Instance(id)
        client = boto3.client('cloudwatch')
        namespace = 'AWS/EC2'
        statistic = 'Average'                   # could be Sum,Maximum,Minimum,SampleCount,Average
        metric_name = 'CPUUtilization'
        cpu = client.get_metric_statistics(
            Period=1 * 60,
            StartTime=datetime.utcnow() - timedelta(seconds=60 * 60),
            EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
            MetricName=metric_name,
            Namespace=namespace,  # Unit='Percent',
            Statistics=[statistic],
            Dimensions=[{'Name': 'InstanceId', 'Value': id}]
        )      
        cpu_stats = []
        for point in cpu['Datapoints']:
            hour = point['Timestamp'].hour
            minute = point['Timestamp'].minute
            time = hour + minute/60
            cpu_stats.append([time,point['Average']])
        cpu_stats = sorted(cpu_stats, key=itemgetter(0))
       # print(cpu['Datapoints'])
        #print(cpu_stats[-1][1])
        if instance.instance_type != "t2.micro":
            if len(cpu_stats) > 0:
                CPU_list.append(cpu_stats[-1][1])
            else:
                CPU_list.append("Initializing")
           
        #   cpu_util=cpu_stats[-1][1]
        #CPU_index+=1
        cnx = get_db()
        cursor = cnx.cursor(buffered=True)
        query = '''Select * from policy'''
        cursor.execute(query)
        if cursor.rowcount > 0:
            row = cursor.fetchone()
            growCPU=row[0]
            shrinkCPU=row[1]
            ratExp=row[2]
            ratShrink=row[3]
            status=row[4]
            if status==0:
                stat="Stopped"
            else: 
               stat="Running"
    
    if error==True:
        return render_template("manager/list.html",title="EC2 Instances",instances=instances,CPU_list=CPU_list,growCPU=growCPU,shrinkCPU=shrinkCPU,ratExp=ratExp,ratShrink=ratShrink,status=stat,error_msg=error_msg)

    else: 
        return render_template("manager/list.html",title="EC2 Instances",instances=instances,CPU_list=CPU_list,growCPU=growCPU,shrinkCPU=shrinkCPU,ratExp=ratExp,ratShrink=ratShrink,status=stat)


@webapp.route('/manager/ec2_autoScale_stop',methods=['GET'])
def ec2_autoScale_stop():
    cnx = get_db()
    print("reach here")
    cursor = cnx.cursor(buffered=True)
    query = '''update policy set running = %s'''
    cursor.execute(query,(0,))
    cnx.commit()
    return redirect(url_for('ec2_list'))


@webapp.route('/manager/delete', methods=['GET'])
def delete():
    cnx = get_db()
    cursor = cnx.cursor(buffered=True)
    query = '''DELETE FROM images'''
    cursor.execute(query)
    cnx.commit()

    # this approach is too slow when the number of images is too big
    # s3 = boto3.resource('s3')
    # bucket = s3.Bucket('ece1779images')
    # for key in bucket.objects.all():
    #     key.delete()
    # run this CLI command in background
    subprocess.Popen(["/usr/bin/aws", "s3", "rm", "s3://ece1779images", "--recursive"])
    
    return redirect(url_for('ec2_list'))
