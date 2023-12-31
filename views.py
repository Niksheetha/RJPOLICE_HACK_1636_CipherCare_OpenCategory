from django.shortcuts import render
from .models import AuthDetails
from keras.models import load_model
from . import parameters as p
from .feature_extraction import get_embedding
import numpy as np
import os
import string 
import random 
import tempfile
import cv2
import math
import sys
from scipy.spatial.distance import euclidean 
import os


def random_string(letter_count, digit_count):  
    str1 = ''.join((random.choice(string.ascii_letters) for x in range(letter_count)))  
    str1 += ''.join((random.choice(string.digits) for x in range(digit_count)))  
  
    sam_list = list(str1)
    random.shuffle(sam_list) 
    final_string = ''.join(sam_list)  
    return final_string  
   


def home(request):
    return render(request, 'home.html')


def encrypt(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        password = request.POST.get('pass')
        audio = request.FILES['audio']
        video_cover_file = request.FILES['video_cover']
        video_hide_file = request.FILES['video_hide']
        print(audio, video_cover_file, video_hide_file)
        enroll_value = enroll(audio)
        destination_directory = 'App/upload'
        os.makedirs(destination_directory, exist_ok=True)

        unique_cover_file_name = os.path.join(destination_directory, 'cover_' + video_cover_file.name)
        unique_hide_file_name = os.path.join(destination_directory, 'hide_' + video_hide_file.name)

        with open(unique_cover_file_name, 'wb') as destination_cover_file:
            for chunk in video_cover_file.chunks():
                destination_cover_file.write(chunk)

        with open(unique_hide_file_name, 'wb') as destination_hide_file:
            for chunk in video_hide_file.chunks():
                destination_hide_file.write(chunk)
        video_name = encode(unique_cover_file_name, unique_hide_file_name)    

        data = AuthDetails(name=name, password=password, audio=enroll_value, video_name = video_name)
        data.save()
        if os.path.isfile(unique_cover_file_name):
            os.remove(unique_cover_file_name)
        
        if os.path.isfile(unique_hide_file_name):
            os.remove(unique_hide_file_name)
        return render(request, 'home.html', {'data': '{}.avi'.format(video_name), 'name': name})

    return render(request, 'home.html')

def enroll(file):
    path = 'App/{}'.format(p.MODEL_FILE)
    try:
        model = load_model(path)
    except:
        print("Failed to load weights from the weights file, please ensure *.pb file is present in the MODEL_FILE directory")
        exit()
    
    enroll_result = get_embedding(model, file, p.MAX_SEC)
    enroll_embs = np.array(enroll_result.tolist())
    speaker = random_string(8,6)

    np.save(os.path.join(p.EMBED_LIST_FILE,speaker +".npy"), enroll_embs)
    print("Succesfully enrolled the user")

    return speaker

model=load_model('App/hide1.h5',compile=False) 

def encode(video_cover, video_hide):
    vidcap1 = cv2.VideoCapture(video_hide)
    vidcap2 = cv2.VideoCapture(video_cover)

    name = random_string(8,6)
    container_outvid = cv2.VideoWriter('App/media/results/{}.avi'.format(name),cv2.VideoWriter_fourcc('H','F','Y','U'), 25, (224,224))
    container = cv2.VideoWriter('App/media/results/{}1.avi'.format(name),cv2.VideoWriter_fourcc('M','J','P','G'), 25, (224,224))
    num_frames = int(vidcap1.get(cv2.CAP_PROP_FRAME_COUNT))
    print("Total frames in secret video:", num_frames)
    secret_batch=[]
    cover_batch=[]
    frame = 0
    while True:

            (success1, secret) = vidcap1.read()
            (success2, cover) = vidcap2.read()

            if not (success1 and success2):
                break       

            secret = cv2.resize(cv2.cvtColor(secret, cv2.COLOR_BGR2RGB), (224,224) ,interpolation=cv2.INTER_AREA)
            cover = cv2.resize(cv2.cvtColor(cover, cv2.COLOR_BGR2RGB), (224,224) ,interpolation=cv2.INTER_AREA)
   
            secret_batch.append(secret)
            cover_batch.append(cover)            
            frame = frame + 1

            if frame % 4 == 0  :
                
                secret_batch = np.float32(secret_batch)/255.0
                cover_batch = np.float32(cover_batch)/255.0
                coverout=model.predict([normalize_batch(secret_batch),normalize_batch(cover_batch)])
                  
                coverout = denormalize_batch(coverout)
                coverout=np.squeeze(coverout)*255.0
                coverout=np.uint8(coverout)

                for i in range(0,4):
                    container_outvid.write(coverout[i][..., ::-1])
                    container.write(coverout[i][..., ::-1])
                secret_batch=[]
                cover_batch=[]
                update_progress(frame, num_frames) 

    print("\n\nSuccessfully encoded video !!!\n")              

    vidcap1.release()
    vidcap2.release()
    cv2.destroyAllWindows()
    return name


def normalize_batch(imgs):
    return (imgs -  np.array([0.485, 0.456, 0.406])) /np.array([0.229, 0.2242, 0.25])

# Denormalize output images                                                        
def denormalize_batch(imgs,should_clip=True):
    imgs= (imgs * np.array([0.229, 0.224, 0.225])) + np.array([0.485, 0.456, 0.406])
    
    if should_clip:
        imgs= np.clip(imgs,0,1)
    return imgs


# Update progress bar
def update_progress(current_frame, total_frames):
    progress=math.ceil((current_frame/total_frames)*100)
    sys.stdout.write('\rProgress: [{0}] {1}%'.format('>'*math.ceil(progress/10), progress))
       

def decrypt(request):
    if request.method == 'POST':
        password = request.POST.get('pass')
        audio = request.FILES['audio']
        video = request.FILES['video']
        video_name = os.path.splitext(video.name)[0] 
        enroll_name = recognize(audio)
        print(enroll_name)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_audio:
            tmp_audio.write(audio.read())

        with tempfile.NamedTemporaryFile(delete=False) as tmp_video:
            tmp_video.write(video.read())
        video_user = AuthDetails.objects.filter(video_name = video_name, audio = enroll_name, password = password)
        if video_user.exists():
            reveal_video(tmp_video.name, video_name) 
            name = AuthDetails.objects.get(video_name = video_name)
            pass

        return render(request, 'decrypt.html' , {'video_name': '{}secret.avi'.format(video_name), 'name': name})
    return render(request, 'decrypt.html')

model1=load_model('App/reveal1.h5',compile=False)

def recognize(file):
    
    if os.path.exists(p.EMBED_LIST_FILE):
        embeds = os.listdir(p.EMBED_LIST_FILE)
    if len(embeds) is 0:
        print("No enrolled users found")
        exit()
    print("Loading model weights from [{}]....".format(p.MODEL_FILE))
    path = 'App/{}'.format(p.MODEL_FILE)
    try:
        model = load_model(path)
    except:
        print("Failed to load weights from the weights file, please ensure *.pb file is present in the MODEL_FILE directory")
        exit()
        
    distances = {}
    print("Processing test sample....")
    print("Comparing test sample against enroll samples....")
    test_result = get_embedding(model, file, p.MAX_SEC)
    test_embs = np.array(test_result.tolist())
    for emb in embeds:
        enroll_embs = np.load(os.path.join(p.EMBED_LIST_FILE,emb))
        speaker = emb.replace(".npy","")
        distance = euclidean(test_embs, enroll_embs)
        distances.update({speaker:distance})
    if min(list(distances.values()))<p.THRESHOLD:
        print("Recognized: ",min(distances, key=distances.get))
        result = min(distances, key=distances.get)
    else:
        print("Could not identify the user, try enrolling again with a clear voice sample")
        print("Score: ",min(list(distances.values())))
        exit()
    return result    
        
   

def reveal_video(video, name):
    vidcap = cv2.VideoCapture(video)
    print("\nDecoding video ...\n")

    num_frames = int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT))
    print("Total frames in container video:", num_frames)


    secret_outvid = cv2.VideoWriter('App/media/results/{}secret.avi'.format(name),cv2.VideoWriter_fourcc('M','J','P','G'), 25, (300,300))
    cover_batch=[]
    frame = 0

    while True:
            (success, cover) = vidcap.read()
            if not (success):
                break       
            cover = cv2.cvtColor(cover, cv2.COLOR_BGR2RGB)       
  
            cover_batch.append(cover)            
            frame = frame + 1
            if frame % 4 == 0  : 
                
                cover_batch = np.float32(cover_batch)/255.0         
                secretout=model1.predict([normalize_batch(cover_batch)])

                secretout=denormalize_batch(secretout)
                secretout=np.squeeze(secretout)*255.0
                secretout=np.uint8(secretout)

                for i in range(0,4):
                    secret_outvid.write(cv2.resize(secretout[i][..., ::-1], (300,300), interpolation=cv2.INTER_CUBIC))
                
                cover_batch=[]

                update_progress(frame, num_frames)

    print("\n\nSuccessfully decoded video !!!\n")

    vidcap.release()
    cv2.destroyAllWindows()