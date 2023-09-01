import openai
import logging
import src.utils as utils
import pandas as pd
import tiktoken
import src.config_loader as config_loader

def initialise(config_file, logging_file, secret_key_file, character_df_file, language_file):
    def setup_openai_secret_key(file_name):
        with open(file_name, 'r') as f:
            api_key = f.readline().strip()
        openai.api_key = api_key

    def setup_logging(file_name):
        logging.basicConfig(filename=file_name, format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        logging.getLogger('').addHandler(console)

    def get_character_df(file_name):
        encoding = utils.get_file_encoding(file_name)
        character_df = pd.read_csv(file_name, engine='python', encoding=encoding)
        character_df = character_df.loc[character_df['voice_model'].notna()]

        return character_df
    
    def get_language_info(file_name):
        language_df = pd.read_csv(file_name)
        try:
            language_info = language_df.loc[language_df['alpha2']==config.language].to_dict('records')[0]
            return language_info
        except:
            logging.error(f"Could not load language '{config.language}'. Please set a valid language in config.ini\n")

    def get_token_limit(llm, custom_token_count):
        if '/' in llm:
            llm = llm.split('/')[-1]

        if llm == 'gpt-3.5-turbo':
            token_limit = 4096
        elif llm == 'gpt-3.5-turbo-16k':
            token_limit = 16384
        elif llm == 'gpt-4':
            token_limit = 8192
        elif llm == 'gpt-4-32k':
            token_limit = 32768
        elif llm == 'claude-2':
            token_limit = 100_000
        elif llm == 'claude-instant-v1':
            token_limit = 100_000
        elif llm == 'palm-2-chat-bison':
            token_limit = 8000
        elif llm == 'palm-2-codechat-bison':
            token_limit = 8000
        elif llm == 'llama-2-13b-chat':
            token_limit = 4096
        elif llm == 'llama-2-70b-chat':
            token_limit = 4096
        elif llm == 'codellama-34b-instruct':
            token_limit = 16000
        elif llm == 'nous-hermes-llama2-13b':
            token_limit = 4096
        elif llm == 'weaver':
            token_limit = 8000
        elif llm == 'mythomax-L2-13b':
            token_limit = 8192
        elif llm == 'airoboros-l2-70b-2.1':
            token_limit = 4096
        else:
            logging.info(f"Could not find number of available tokens for {llm}. Defaulting to token count of {custom_token_count} (this number can be changed via the `custom_token_count` setting in config.ini)")
            token_limit = custom_token_count
        
        if token_limit <= 4096:
            logging.info(f"{llm} has a low token count of {token_limit}. For better NPC memories, try changing to a model with a higher token count")
        
        return token_limit

    config = config_loader.ConfigLoader(config_file)
    setup_logging(logging_file)
    setup_openai_secret_key(secret_key_file)
    logging.info(f"Running Mantella with '{config.llm}'. The language model chosen can be changed via config.ini")

    # clean up old instances of exe runtime files
    utils.cleanup_mei(config.remove_mei_folders)
    
    character_df = get_character_df(character_df_file)
    language_info = get_language_info(language_file)
    chosenmodel = config.llm
    if 'openrouter' in config.alternative_openai_api_base:
        chosenmodel = 'gpt-3.5-turbo'
    encoding = tiktoken.encoding_for_model(chosenmodel)
    token_limit = get_token_limit(config.llm, config.custom_token_count)
    if config.alternative_openai_api_base != 'none':
        openai.api_base = config.alternative_openai_api_base

    return config, character_df, language_info, encoding, token_limit