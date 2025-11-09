# EventSync

## Set Up Enviornment
In EventSync directory, create two enviornment file name .env and env.yaml:  
Replace string inside " " with keys
  
.env
```
PROJECT_ID="___"
REGION="___"
INSTANCE_CONNECTION_NAME="___"
DB_USER="___"
DB_PASS="___"
DB_NAME="___"
```

env.yaml
```
INSTANCE_CONNECTION_NAME: "___"
DB_USER: "___"
DB_PASS: "___"
DB_NAME: "___"
```


You need to add env variables to enviornment everytime you open a new terminal.

Windows:
```
.\load_env.ps1
```

Mac\Linux:
```
source .env
```

Google Cloud Setup
```
gcloud init
gcloud config set project $env:PROJECT_ID
```

## Local Testing

### Cloud SQL Proxy
Setup a cloud sql proxy in a separate terminal. You will need this on while doing local development.

Windows:
```
.\cloud-sql-proxy.exe --address 127.0.0.1 --port 3306 $env:INSTANCE_CONNECTION_NAME
```

Mac/Linux:  
Follow instructions here to download and run proxy.
https://docs.cloud.google.com/sql/docs/mysql/sql-proxy

### Docker

Start Docker Engine


Build Image:
```
docker build -t eventsync-flask:local .
```

Run Container:
```
docker run --rm -p 5000:8080 `
  -e DB_USER=$env:DB_USER `
  -e DB_PASS=$env:DB_PASS `
  -e DB_NAME=$env:DB_NAME `
  -e INSTANCE_CONNECTION_NAME=$env:INSTANCE_CONNECTION_NAME `
  -e DB_HOST=host.docker.internal `
  -e DB_PORT=3306 `
  eventsync-flask:local
```

## Deploy to Cloud

Tag & push to Artifact Registry
```
docker tag eventsync-flask:local $env:REGION-docker.pkg.dev/$env:PROJECT_ID/webapps/eventsync-flask:v1
gcloud auth configure-docker $env:REGION-docker.pkg.dev
docker push $env:REGION-docker.pkg.dev/$env:PROJECT_ID/webapps/eventsync-flask:v1
```

Deploy to Cloud Run
```
gcloud run deploy flask-mysql-demo `
  --image=$env:REGION-docker.pkg.dev/$env:PROJECT_ID/webapps/eventsync-flask:v1 `
  --region=$env:REGION `
  --platform=managed `
  --allow-unauthenticated `
  --add-cloudsql-instances=$env:INSTANCE_CONNECTION_NAME
  --env-vars-file=env.yaml
```