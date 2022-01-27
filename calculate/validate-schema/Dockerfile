FROM alpine:3.15.0

WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install --no-cache --upgrade pip setuptools jsonschema==4.4.0
ENTRYPOINT ["jsonschema"]
CMD ["--help"]