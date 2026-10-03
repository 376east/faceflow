"""Render a montage of manually captured real UI states. No browser automation here."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
import numpy as np,json,wave,subprocess,math,argparse,shutil

ROOT=Path(__file__).resolve().parents[1];D=ROOT/'demo';W,H=1920,1080;FPS=60
INK='#171a18';BG='#f8f9f5';LIME='#c1f452';MUTED='#626860'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ffmpeg',default='ffmpeg');parser.add_argument('--font');parser.add_argument('--bold-font');parser.add_argument('--preview',action='store_true');args=parser.parse_args()
    regular=args.font or ('C:/Windows/Fonts/segoeui.ttf' if Path('C:/Windows/Fonts/segoeui.ttf').exists() else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold=args.bold_font or ('C:/Windows/Fonts/segoeuib.ttf' if Path('C:/Windows/Fonts/segoeuib.ttf').exists() else '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')
    fonts={}
    def font(size,strong=False):
        key=(size,strong)
        if key not in fonts:fonts[key]=ImageFont.truetype(bold if strong else regular,size)
        return fonts[key]
    scenes=json.loads((D/'scenes.json').read_text(encoding='utf-8'));start=0
    for s in scenes:s['start']=start;start+=s['duration']
    images={}
    for s in scenes:
        if s.get('frame'):
            im=Image.open(D/'frames'/s['frame']).convert('RGB');padded=Image.new('RGB',(1440,max(900,im.height)),BG);padded.paste(im,(0,0));images[s['name']]=padded
    portrait=Image.open(D/'synthetic/person-a.png').convert('RGB')
    def wrap(text,size,width,strong=False):
        lines=[];line=''
        for word in text.split():
            trial=(line+' '+word).strip()
            if line and font(size,strong).getlength(trial)>width:lines.append(line);line=word
            else:line=trial
        return lines+[line]
    def render(s,t):
        canvas=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(canvas);d.text((64,34),'FaceFlow',font=font(32,True),fill=INK)
        d.text((1400,45),'СИНТЕТИЧЕСКИЕ ДАННЫЕ',font=font(17),fill=MUTED)
        if not s.get('frame'):
            d.text((64,220),'ТВОИ' if s['name']=='intro' else 'FaceFlow',font=font(150,True),fill=INK)
            d.text((64,390),'КАДРЫ.' if s['name']=='intro' else 'Свои кадры.',font=font(110,True),fill=INK)
            d.rectangle((72,550,290,563),fill=LIME)
            for i,line in enumerate(wrap('Селфи → поиск → выбор → скачать.',32,950)):d.text((72,625+i*40),line,font=font(32),fill=INK)
            canvas.paste(ImageOps.fit(portrait,(520,650)),(1270,175));d=ImageDraw.Draw(canvas)
            d.text((72,825),'Персонажи вымышленные. Показ интерфейса, не оценка точности.',font=font(23),fill=MUTED)
        else:
            d.text((64,128),s['role'],font=font(18),fill=MUTED);y=220
            for line in wrap(s['title'],56,300,True):d.text((64,y),line,font=font(56,True),fill=INK);y+=68
            d.rectangle((65,y+25,160,y+33),fill=LIME)
            image=images[s['name']]
            if s['name']=='selected' and t<1.3:image=images['results']
            canvas.paste(image.crop((0,s.get('crop',0),1440,s.get('crop',0)+840)),(400,105));d=ImageDraw.Draw(canvas)
            d.rectangle((399,104,1840,945),outline='#d9ddd4',width=1)
            if s['name']=='selected' and t>4.2:
                d.rounded_rectangle((64,755,345,850),radius=12,fill=LIME);d.text((82,775),'ZIP: 1 КАДР',font=font(26,True),fill=INK)
        if .35<=t<=.35+s['voice_duration']:
            for i,line in enumerate(wrap(s['speech'],24,1380)):d.text((400,970+i*30),line,font=font(24),fill=INK)
        d.rectangle((64,1058,1856,1061),fill='#d9ddd4');d.rectangle((64,1058,64+round(1792*(s['start']+t)/start),1061),fill=INK)
        return canvas
    samples=[render(s,min(2,s['duration']/2)) for s in scenes]
    samples[0].save(D/'poster.png')
    for i,im in enumerate(samples):im.save(ROOT/'work'/f'demo-preview-{i}.jpg',quality=94)
    if args.preview:return
    sr=48000;n=round(start*sr);voice=np.zeros(n,np.float32);music=np.zeros(n,np.float32);rng=np.random.default_rng(104)
    beat=60/112
    def add(at,x):
        i=round(at*sr);length=min(len(x),n-i)
        if 0<=i<n:music[i:i+length]+=x[:length]
    for k in range(math.ceil(start/beat)):
        tt=np.arange(int(.26*sr))/sr;freq=46+80*np.exp(-tt*30);add(k*beat,np.sin(2*np.pi*np.cumsum(freq)/sr)*np.exp(-tt*16)*.06)
        tt=np.arange(int(.065*sr))/sr;add((k+.5)*beat,rng.normal(0,1,len(tt))*np.exp(-tt*85)*.004)
    notes=[146.83,220,293.66,329.63,185,220,293.66,369.99]
    for k in range(math.ceil(start/(beat*.5))):
        tt=np.arange(int(.5*sr))/sr;add(k*beat*.5,np.sin(2*np.pi*notes[k%8]*tt)*np.exp(-tt*9)*.015)
    for s in scenes:
        with wave.open(str(D/'narration'/s['wav'])) as f:
            assert (f.getframerate(),f.getnchannels(),f.getsampwidth())==(sr,1,2)
            a=np.frombuffer(f.readframes(f.getnframes()),np.int16).astype(np.float32)/32768
        i=round((s['start']+.35)*sr);a*=.68/max(.001,float(np.max(abs(a))));voice[i:i+len(a)]+=a;music[max(0,i-2880):min(n,i+len(a)+4800)]*=.6
    fade=np.minimum(1,np.arange(n)/(sr*.15))*np.minimum(1,(n-1-np.arange(n))/(sr*.45))
    soundtrack=ROOT/'work/demo-soundtrack.wav'
    with wave.open(str(soundtrack),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes(((voice+music*fade).clip(-.95,.95)*32767).astype(np.int16).tobytes())
    p=subprocess.Popen([args.ffmpeg,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r',str(FPS),'-i','pipe:0','-i',str(soundtrack),'-c:v','libx264','-crf','16','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart','-shortest',str(D/'faceflow-demo.mp4')],stdin=subprocess.PIPE)
    for s in scenes:
        for frame in range(round(s['duration']*FPS)):p.stdin.write(render(s,frame/FPS).tobytes())
        print(s['name'],'encoded',flush=True)
    p.stdin.close();assert p.wait()==0
    print('Rendered',start,'seconds')

if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True);main()
