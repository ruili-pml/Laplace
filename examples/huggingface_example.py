from collections.abc import MutableMapping
from collections import UserDict
import numpy
import torch
from torch import nn
import torch.utils.data as data_utils

from laplace import Laplace

import logging
import warnings

logging.basicConfig(level='ERROR')
warnings.filterwarnings('ignore')

from transformers import (  # noqa: E402
    GPT2Config,
    GPT2ForSequenceClassification,
    GPT2Tokenizer,
    DataCollatorWithPadding,
    PreTrainedTokenizer,
)
from peft import LoraConfig, get_peft_model  # noqa: E402
from datasets import Dataset  # noqa: E402


# make deterministic
torch.manual_seed(0)
numpy.random.seed(0)

tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
tokenizer.pad_token_id = tokenizer.eos_token_id

data = [
    {'text': 'Today is hot, but I will manage!!!!', 'label': 1},
    {'text': 'Tomorrow is cold', 'label': 0},
    {'text': 'Carpe diem', 'label': 1},
    {'text': 'Tempus fugit', 'label': 1},
]
dataset = Dataset.from_list(data)


def tokenize(row):
    return tokenizer(row['text'])


dataset = dataset.map(tokenize, remove_columns=['text'])
dataset.set_format(type='torch', columns=['input_ids', 'attention_mask', 'label'])
dataloader = data_utils.DataLoader(
    dataset, batch_size=100, collate_fn=DataCollatorWithPadding(tokenizer)
)

data = next(iter(dataloader))
print(
    f'Huggingface data defaults to UserDict, which is a MutableMapping? {isinstance(data, UserDict)}'
)
for k, v in data.items():
    print(k, v.shape)


class MyGPT2(nn.Module):
    """
    Huggingface LLM wrapper.

    Args:
        tokenizer: The tokenizer used for preprocessing the text data. Needed
            since the model needs to know the padding token id.
    """

    def __init__(self, tokenizer: PreTrainedTokenizer) -> None:
        super().__init__()
        config = GPT2Config.from_pretrained('gpt2')
        config.pad_token_id = tokenizer.pad_token_id
        config.num_labels = 2
        self.hf_model = GPT2ForSequenceClassification.from_pretrained(
            'gpt2', config=config
        )

    def forward(self, data: MutableMapping) -> torch.Tensor:
        """
        Custom forward function. Handles things like moving the
        input tensor to the correct device inside.

        Args:
            data: A dict-like data structure with `input_ids` inside.
                This is the default data structure assumed by Huggingface
                dataloaders.

        Returns:
            logits: An `(batch_size, n_classes)`-sized tensor of logits.
        """
        device = next(self.parameters()).device
        input_ids = data['input_ids'].to(device)
        attn_mask = data['attention_mask'].to(device)
        output_dict = self.hf_model(input_ids=input_ids, attention_mask=attn_mask)
        return output_dict.logits


model = MyGPT2(tokenizer)

# Last-layer Laplace on the foundation model itself
# -------------------------------------------------
model.eval()

# Enable grad only for the last layer
for p in model.hf_model.parameters():
    p.requires_grad = False

for p in model.hf_model.score.parameters():
    p.requires_grad = True

la = Laplace(
    model,
    likelihood='classification',
    # Will only hit the last-layer since it's the only one that is grad-enabled
    subset_of_weights='all',
    hessian_structure='diag',
)
la.fit(dataloader)
la.optimize_prior_precision()

X_test = next(iter(dataloader))
print(f'[Foundation Model] The predictive tensor is of shape: {la(X_test).shape}.')

del model
del la


# Laplace on the LoRA-attached LLM
# --------------------------------


def get_lora_model():
    model = MyGPT2(tokenizer)  # Note we don't disable grad
    config = LoraConfig(
        r=4,
        lora_alpha=16,
        target_modules=['c_attn'],  # LoRA on the attention weights
        lora_dropout=0.1,
        bias='none',
    )
    lora_model = get_peft_model(model, config)
    return lora_model


lora_model = get_lora_model()
# Train it as usual

lora_model.eval()

lora_la = Laplace(
    lora_model,
    likelihood='classification',
    subset_of_weights='all',
    hessian_structure='diag',
)

X_test = next(iter(dataloader))
print(f'[LoRA-LLM] The predictive tensor is of shape: {lora_la(X_test).shape}.')
