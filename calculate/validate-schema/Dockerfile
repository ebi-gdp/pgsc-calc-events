FROM python:3.8-slim-buster

WORKDIR /app
RUN pip3 install jsonschema==4.4.0
COPY calculate-schema.json calculate-schema.json
ENTRYPOINT ["jsonschema"]
CMD ["--help"]