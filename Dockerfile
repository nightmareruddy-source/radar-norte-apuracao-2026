FROM python:3.13-slim
WORKDIR /app
COPY . /app
EXPOSE 8080
# Container bind is external by necessity. Put authentication/reverse proxy in front before public Internet exposure.
CMD ["python","radar_norte.py","--host","0.0.0.0","--port","8080","--refresh","60"]
