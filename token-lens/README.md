# TokenLens

A local token visualizer for GPT and Claude models — like [OpenAI's Tokenizer](https://platform.openai.com/tokenizer), but everything runs in your browser. Your text never leaves your machine.

## What it does

Paste or type any text and TokenLens will show you exactly how an LLM sees it: each token highlighted in a distinct colour, with a live count of tokens, characters, and words. There's also a context window bar showing how much of a model's limit your text consumes.

This is useful when you're:
- Estimating API costs before sending a request
- Debugging why a prompt behaves unexpectedly at the edges of a context window
- Understanding how the model "reads" code, punctuation, or non-English text

## Usage

Just open `token-counter.html` in any browser. No server, no install, no account.

1. Select an encoding matching the model you're targeting
2. Paste your text into the input box
3. Watch the visualization update in real time

## Privacy

TokenLens loads the tokenizer library from [unpkg.com](https://unpkg.com) on first open (one-time CDN request), then all tokenization happens locally in your browser. Your input is never sent anywhere.

## Credits

Tokenization powered by [gpt-tokenizer](https://github.com/niieani/gpt-tokenizer), a pure JavaScript port of OpenAI's tiktoken.