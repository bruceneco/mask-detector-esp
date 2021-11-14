import random
import time

from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.models import load_model
from imutils import url_to_image
import numpy as np
import imutils
import cv2
from paho.mqtt import client as mqtt_client

# Load models
prototxtPath = r"face_detector/deploy.prototxt"
weightsPath = r"face_detector/res10_300x300_ssd_iter_140000.caffemodel"
faceNet = cv2.dnn.readNet(prototxtPath, weightsPath)
maskNet = load_model("mask_detector.model")

# Set up MQTT
broker = 'localhost'
port = 1883
topic_signal = "mask-detector/signal"
topic_result = 'mask-detector/result'
client_id = f'jose-neco-41990145'


def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)

    # Set Connecting Client ID
    client = mqtt_client.Client(client_id)
    client.on_connect = on_connect
    client.connect(broker, port)
    return client


def detect_and_predict_mask(frame, face_net, mask_net):
    # grab the dimensions of the frame and then construct a blob
    # from it
    (h, w) = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(frame, 1.0, (224, 224),
                                 (104.0, 177.0, 123.0))

    # pass the blob through the network and obtain the face detections
    face_net.setInput(blob)
    detections = face_net.forward()

    # initialize our list of faces, their corresponding locations,
    # and the list of predictions from our face mask network
    faces = []
    locs = []
    preds = []

    # loop over the detections
    for i in range(0, detections.shape[2]):
        # extract the confidence (i.e., probability) associated with
        # the detection
        confidence = detections[0, 0, i, 2]

        # filter out weak detections by ensuring the confidence is
        # greater than the minimum confidence
        if confidence > 0.5:
            # compute the (x, y)-coordinates of the bounding box for
            # the object
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (startX, startY, endX, endY) = box.astype("int")

            # ensure the bounding boxes fall within the dimensions of
            # the frame
            (startX, startY) = (max(0, startX), max(0, startY))
            (endX, endY) = (min(w - 1, endX), min(h - 1, endY))

            # extract the face ROI, convert it from BGR to RGB channel
            # ordering, resize it to 224x224, and preprocess it
            face = frame[startY:endY, startX:endX]
            face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            face = cv2.resize(face, (224, 224))
            face = img_to_array(face)
            face = preprocess_input(face)

            # add the face and bounding boxes to their respective
            # lists
            faces.append(face)
            locs.append((startX, startY, endX, endY))

    # only make a predictions if at least one face was detected
    if len(faces) > 0:
        # for faster inference we'll make batch predictions on *all*
        # faces at the same time rather than one-by-one predictions
        # in the above `for` loop
        faces = np.array(faces, dtype="float32")
        preds = mask_net.predict(faces, batch_size=32)

    # return a 2-tuple of the face locations and their corresponding
    # locations
    return locs, preds


def take_picture():
    print('[INFO] Taking picture...')
    picture = url_to_image(url='http://192.168.0.118/cam-hi.jpg')
    return imutils.resize(picture, width=400)


def get_diagnosis():
    frame = take_picture()
    (locs, pred) = detect_and_predict_mask(frame, faceNet, maskNet)
    if type(pred) != list and pred.all():
        (mask, without_mask) = pred[0]
        return 1 if mask > without_mask else 2
    else:
        return 0


def subscribe_signal(client):
    def on_message(client, userdata, msg):
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        publish_result(client)

    client.subscribe(topic_signal)
    client.on_message = on_message


def publish_result(client):
    sent = False
    while not sent:
        msg = get_diagnosis()
        result = client.publish(topic_result, msg)
        status = result[0]
        if status == 0:
            sent = True
            print(f"Send `{msg}` to topic `{topic_result}`")
        else:
            print(f"Failed to send message to topic {topic_result}")
        time.sleep(1)


def main():
    instance_client = connect_mqtt()
    subscribe_signal(instance_client)
    instance_client.loop_forever()


if __name__ == '__main__':
    main()
