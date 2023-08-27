import requests
import winsound
import logging
import src.utils as utils
import os
import soundfile as sf
import numpy as np
import re
import pandas as pd
import sys
import json
import subprocess

class VoiceModelNotFound(Exception):
    pass

class Synthesizer:
    def __init__(self, config):
        self.check_if_xvasynth_is_running()

        self.xvasynth_path = config.xvasynth_path
        # voice models path
        self.model_path = f"{self.xvasynth_path}/resources/app/models/skyrim/"
        # output wav / lip files path
        self.output_path = utils.resolve_path('data')+'/data'

        self.language = config.language

        # determines whether the voiceline should play internally
        self.debug_mode = config.debug_mode
        self.play_audio_from_script = config.play_audio_from_script

        # last active voice model
        self.last_voice = ''

        self.model_type = ''
        self.base_speaker_emb = ''

        self.synthesize_url = 'http://127.0.0.1:8008/synthesize'
        self.synthesize_batch_url = 'http://127.0.0.1:8008/synthesize_batch'
        self.loadmodel_url = 'http://127.0.0.1:8008/loadModel'
        self.setvocoder_url = 'http://127.0.0.1:8008/setVocoder'
    

    def synthesize(self, voice, voice_folder, voiceline):
        if voice != self.last_voice:
            logging.info('Loading voice model...')
            self._change_voice(voice)
            logging.info('Voice model loaded.')

        logging.info(f'Synthesizing voiceline: {voiceline}')
        phrases = self._split_voiceline(voiceline)

        # make voice model folder if it doesn't already exist
        if not os.path.exists(f"{self.output_path}/voicelines/{self.last_voice}"):
            os.makedirs(f"{self.output_path}/voicelines/{self.last_voice}")
        
        voiceline_files = []
        for phrase in phrases:
            voiceline_file = f"{self.output_path}/voicelines/{self.last_voice}/{utils.clean_text(phrase)[:150]}.wav"
            voiceline_files.append(voiceline_file)

        final_voiceline_file_name = 'voiceline'
        final_voiceline_file =  f"{self.output_path}/voicelines/{self.last_voice}/{final_voiceline_file_name}.wav"

        if os.path.exists(final_voiceline_file):
            os.remove(final_voiceline_file)
        if os.path.exists(final_voiceline_file.replace(".wav", ".lip")):
            os.remove(final_voiceline_file.replace(".wav", ".lip"))

        # Synthesize voicelines
        if len(phrases) == 1:
            self._synthesize_line(phrases[0], final_voiceline_file)
        else:
            # TODO: include batch synthesis for v3 models (batch not needed very often)
            if self.model_type != 'xVAPitch':
                self._batch_synthesize(phrases, voiceline_files)
            else:
                for i, voiceline_file in enumerate(voiceline_files):
                    self._synthesize_line(phrases[i], voiceline_files[i])
            self.merge_audio_files(voiceline_files, final_voiceline_file)

        # generate .lip file
        self.run_command(f'{self.xvasynth_path}/resources/app/plugins/lip_fuz/FaceFXWrapper.exe "Skyrim" "USEnglish" "{self.xvasynth_path}/resources/app/plugins/lip_fuz/FonixData.cdf" "{final_voiceline_file}" "{final_voiceline_file.replace(".wav", "_r.wav")}" "{final_voiceline_file.replace(".wav", ".lip")}" "{voiceline}"')

        # remove file created by FaceFXWrapper
        if os.path.exists(final_voiceline_file.replace(".wav", "_r.wav")):
            os.remove(final_voiceline_file.replace(".wav", "_r.wav"))

        if (self.debug_mode == '1') & (self.play_audio_from_script == '1'):
            winsound.PlaySound(final_voiceline_file, winsound.SND_FILENAME)

        return final_voiceline_file
    

    @utils.time_it
    def _group_sentences(self, voiceline_sentences, max_length=150):
        """
        Splits sentences into separate voicelines based on their length (max=max_length)
        Groups sentences if they can be done so without exceeding max_length
        """
        grouped_sentences = []
        temp_group = []
        for sentence in voiceline_sentences:
            if len(sentence) > max_length:
                grouped_sentences.append(sentence)
            elif len(' '.join(temp_group + [sentence])) <= max_length:
                temp_group.append(sentence)
            else:
                grouped_sentences.append(' '.join(temp_group))
                temp_group = [sentence]
        if temp_group:
            grouped_sentences.append(' '.join(temp_group))

        return grouped_sentences
    

    @utils.time_it
    def _split_voiceline(self, voiceline, max_length=150):
        """Split voiceline into phrases by commas, 'and', and 'or'"""

        # Split by commas and "and" or "or"
        chunks = re.split(r'(, | and | or )', voiceline)
        # Join the delimiters back to their respective chunks
        chunks = [chunks[i] + (chunks[i+1] if i+1 < len(chunks) else '') for i in range(0, len(chunks), 2)]
        # Filter out empty chunks
        chunks = [chunk for chunk in chunks if chunk.strip()]

        result = []
        for chunk in chunks:
            if len(chunk) <= max_length:
                if result and result[-1].endswith(' and'):
                    result[-1] = result[-1][:-4]
                    chunk = 'and ' + chunk.strip()
                elif result and result[-1].endswith(' or'):
                    result[-1] = result[-1][:-3]
                    chunk = 'or ' + chunk.strip()
                result.append(chunk.strip())
            else:
                # Split long chunks based on length
                words = chunk.split()
                current_line = words[0]
                for word in words[1:]:
                    if len(current_line + ' ' + word) <= max_length:
                        current_line += ' ' + word
                    else:
                        if current_line.endswith(' and'):
                            current_line = current_line[:-4]
                            word = 'and ' + word
                        if current_line.endswith(' or'):
                            current_line = current_line[:-3]
                            word = 'or ' + word
                        result.append(current_line.strip())
                        current_line = word
                result.append(current_line.strip())

        result = self._group_sentences(result, max_length)
        logging.info(f'Split sentence into : {result}')

        return result
    

    def merge_audio_files(self, audio_files, voiceline_file_name):
        merged_audio = np.array([])

        for audio_file in audio_files:
            try:
                audio, samplerate = sf.read(audio_file)
                merged_audio = np.concatenate((merged_audio, audio))
            except:
                logging.info(f'Could not find voiceline file: {audio_file}')

        sf.write(voiceline_file_name, merged_audio, samplerate)
    

    @utils.time_it
    def _synthesize_line(self, line, save_path):
        data = {
            'pluginsContext': '{}',
            'modelType': self.model_type,
            'sequence': line,
            'pace': 1,
            'outfile': save_path,
            'vocoder': 'n/a',
            'base_lang': self.language,
            'base_emb': self.base_speaker_emb,
            'useSR': False,
            'useCleanup': False, 
        }
        requests.post(self.synthesize_url, json=data)


    @utils.time_it
    def _batch_synthesize(self, grouped_sentences, voiceline_files):
        # line = [text, unknown 1, unknown 2, pace, output_path, unknown 5, unknown 6, pitch_amp]
        linesBatch = [[grouped_sentences[i], '', '', 1, voiceline_files[i], '', '', 1] for i in range(len(grouped_sentences))]
        
        data = {
            'pluginsContext': '{}',
            'modelType': self.model_type,
            'linesBatch': linesBatch,
            'speaker_i': None,
            'vocoder': [],
            'outputJSON': None,
            'useSR': None,
            'useCleanup': None,
        }
        requests.post(self.synthesize_batch_url, json=data)


    @utils.time_it
    def check_if_xvasynth_is_running(self):
        try:
            response = requests.get('http://127.0.0.1:8008/')
            response.raise_for_status()  # If the response contains an HTTP error status code, raise an exception
        except requests.exceptions.RequestException as err:
            logging.error('Could not connect to xVASynth. Ensure that xVASynth is running and try again.')
            input("Press Enter to exit.")
            sys.exit(0)
        
    
    @utils.time_it
    def _change_voice(self, voice):
        voice_path = f"{self.model_path}sk_{voice.lower().replace(' ', '')}"
        if not os.path.exists(voice_path+'.json'):
            logging.error(f"Voice model does not exist in location '{voice_path}'. Please ensure that the correct path has been set in config.ini (xvasynth_folder) and that the model has been downloaded from https://www.nexusmods.com/skyrimspecialedition/mods/44184?tab=files (Ctrl+F for 'sk_{voice.lower().replace(' ', '')}').")
            raise VoiceModelNotFound()

        with open(voice_path+'.json', 'r') as f:
            voice_model_json = json.load(f)

        try:
            base_speaker_emb = voice_model_json['games'][0]['base_speaker_emb']
            base_speaker_emb = str(base_speaker_emb).replace('[','').replace(']','')
        except:
            base_speaker_emb = None

        self.base_speaker_emb = base_speaker_emb
        self.model_type = voice_model_json.get('modelType')
        
        model_change = {
            'outputs': None,
            'version': '3.0',
            'model': voice_path, 
            'modelType': self.model_type,
            'base_lang': self.language, 
            'pluginsContext': '{}',
        }
        requests.post(self.loadmodel_url, json=model_change)

        self.last_voice = voice


    def run_command(self, command):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        sp = subprocess.Popen(command, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stdout, stderr = sp.communicate()
        stderr = stderr.decode("utf-8")