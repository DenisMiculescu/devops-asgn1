###########################################
#                Imports                  #
###########################################

# Required library imports
import boto3
import webbrowser
import time
import subprocess
import json
import requests
import random
import string

# Setting up AWS EC2 and S3 resources
ec2 = boto3.resource("ec2")
s3 = boto3.resource("s3")

# Generates a random 6 character string for naming the EC2 instance and S3 bucket
random_chars = "".join(
    random.choice(string.ascii_lowercase + string.digits) for x in range(6)
)
# Name tag for the bucket
bucket_name = f"{random_chars}-dmiculescu"

###########################################
#           EC2 Metadata Script           #
###########################################

# This script installs and starts a HTTP server, then creates a HTML page showing some metadata of the instance
user_data = """#!/bin/bash
    yum install httpd -y
    systemctl enable httpd
    systemctl start httpd
    cat << EOF > /var/www/html/index.html
    <!DOCTYPE html>
    <html>
        <head>
            <title>EC2 Instance</title>
        </head>
        <body>
            <h1>Meta-Data</h1>
            <h3>Instance ID: $(curl -s http://169.254.169.254/latest/meta-data/instance-id)</h3>
            <h3>Instance Private IP: $(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)</h3>
            <h3>Availibility zone: $(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone)</h3>
            <h3>Instance Type: $(curl -s http://169.254.169.254/latest/meta-data/instance-type)</h3>
        </body>
    </html>
EOF
    """


###########################################
#         EC2 Instance Creation           #
###########################################

# Name tag for the EC2 instance
tag_name = f"WebServer-{random_chars}"

# Creates a new EC2 instance with specified configurations
new_instances = ec2.create_instances(
    ImageId="ami-03eb6185d756497f8",
    MinCount=1,
    MaxCount=1,
    InstanceType="t2.nano",
    UserData=user_data,
    KeyName="DM_Key",
    SecurityGroups=["DM_SecurityGroup"],
    TagSpecifications=[
        {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": tag_name}]}
    ],
)

# Shows user that EC2 is in the process of being created
print("Creating EC2 instance...")

# Waits until EC2 instance is running and refreshes the data
new_instances[0].wait_until_running()
new_instances[0].reload()

# Gets the public IP of the created instance
public_ipv4 = new_instances[0].public_ip_address

# Confirms EC2 instance is up and running
print(f"EC2 instance created with ID: {new_instances[0].id}\n")

# Checks if the `public_ipv4` variable is either empty (or None) or has the value "none".
if not public_ipv4 or public_ipv4 == "none":
    print("Error: Unable to retrieve public IP of the EC2 instance.")
    exit()

###########################################
#                SCP & SSH                #
###########################################

# Notify user about transfer of the monitoring script
print(f"Transferring monitor.sh to EC2 instance with IP {public_ipv4}...")

# Uses SCP to transfer the monitor script to the EC2 instance
subprocess.run(
    f"scp -o StrictHostKeyChecking=no -i DM_Key.pem monitor.sh ec2-user@{public_ipv4}:~/",
    shell=True,
)

# Informs user about script execution
print("\nTransferred monitor.sh. Now executing it on the EC2 instance...")

# SSH into the EC2 instance and execute the monitoring script
subprocess.run(
    f"ssh -o StrictHostKeyChecking=no -i DM_Key.pem ec2-user@{public_ipv4} ./monitor.sh",
    shell=True,
)

# Confirms execution of script
print("monitor.sh executed\n")


###########################################
#           S3 Bucket Creation            #
###########################################


# Notify user about the creation of the S3 bucket
print(f"Creating S3 bucket with name: {bucket_name}...")

# Creates an S3 bucket with the randomly generated name
new_buckets = s3.create_bucket(Bucket=bucket_name)

# Confirm creation of S3 bucket
print(f"S3 bucket {bucket_name} created.\n")


###########################################
#           S3 Bucket Policy              #
###########################################

# Creates a client for the S3 bucket
s3client = boto3.client("s3")

# Removes public access block from the bucket
s3client.delete_public_access_block(Bucket=bucket_name)

# Sets a policy for the created bucket to allow public read access
bucket_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": f"arn:aws:s3:::{bucket_name}/*",
        }
    ],
}

s3.Bucket(bucket_name).Policy().put(Policy=json.dumps(bucket_policy))


###########################################
#    Image retrieval & Website Config.    #
###########################################

# Retrives an image from the internet
response = requests.get("http://devops.witdemo.net/logo.jpg")

# Defines the website configuration for the bucket
website_configuration = {
    "ErrorDocument": {"Key": "error.html"},
    "IndexDocument": {"Suffix": "index.html"},
}

# Applies the website configuration to the S3 bucket
bucket_website = s3.BucketWebsite(bucket_name)
bucket_website.put(WebsiteConfiguration=website_configuration)

# If the image was retrieved successfully, it gets uploaded to the S3 bucket
if response.status_code == 200:
    s3client.put_object(Body=response.content, Bucket=bucket_name, Key="image.jpg")


###########################################
#              S3 Bucket HTML             #
###########################################

# Creates a HTML file referencing the uploaded image
html = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>S3 Bucket</title>
        </head>
        <body>
            <img src="image.jpg">
        </body>
    </html>
"""

s3client.put_object(
    Body=html, Bucket=bucket_name, Key="index.html", ContentType="text/html"
)


###########################################
#                  URLs                   #
###########################################

# Waiting for 15 seconds
time.sleep(15)

# URLs for the EC2 and S3 websites
url1 = f"http://{public_ipv4}"
url2 = f"http://{bucket_name}.s3-website-us-east-1.amazonaws.com"


# Continuously checks the EC2 website unitl it's up and the opens it in a browser
while True:
    try:
        response = requests.get(url1)
        if response.status_code == 200:
            # Notifes user about opening EC2 website
            print(f"Opening EC2 web server at {url1} in browser...")
            webbrowser.open(url1)
            break
        else:
            print("Waiting for web server to start...")
    except requests.exceptions.RequestException as e:
        print("Waiting for web server to start...")


# Notify user about S3 Bucket website opening
print(f"Opening S3 website at {url2} in browser...")

# Opens the S3 website in a browser
webbrowser.open(url2)
