"""Optional online regeneration; the renderer itself uses checked-in WAV files."""
from pathlib import Path
import asyncio,json,subprocess,wave,math,argparse
import edge_tts
ROOT=Path(__file__).resolve().parents[1]

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ffmpeg',default='ffmpeg');args=parser.parse_args()
    path=ROOT/'demo/scenes.json';scenes=json.loads(path.read_text(encoding='utf-8'));(ROOT/'work').mkdir(exist_ok=True)
    for s in scenes:
        text=s['speech'].replace('ё','е').replace('Ё','Е');s['speech']=text
        mp3=ROOT/'work'/f"{s['name']}.mp3";wav=ROOT/'demo/narration'/s['wav']
        await edge_tts.Communicate(text,'ru-RU-SvetlanaNeural',rate='+0%').save(str(mp3))
        subprocess.run([args.ffmpeg,'-y','-v','error','-i',str(mp3),'-ar','48000','-ac','1',str(wav)],check=True)
        with wave.open(str(wav)) as f:duration=f.getnframes()/f.getframerate()
        s['voice_duration']=duration;s['duration']=math.ceil((duration+.8)*60)/60
    path.write_text(json.dumps(scenes,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
