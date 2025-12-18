from transformers.models.gpt2.modeling_gpt2 import GPT2Block

class GPT2BlockWithAdapter(GPT2Block):
    def __init__(self, config):
        super().__init__(config)
        # Assume the size of the Adapter is 64
        adapter_size = 64
        self.adapter = AdapterLayer(config.n_embd, adapter_size)

    def forward(
        self,
        hidden_states,
        layer_past=None,
        attention_mask=None,
        head_mask=None,
        use_cache=False,
        output_attentions=False,
    ):
        # Call the original forward pass method
        attn_outputs = super().forward(
            hidden_states,
            layer_past=layer_past,
            attention_mask=attention_mask,
            head_mask=head_mask,
            use_cache=use_cache,
            output_attentions=output_attentions,
        )
        # Get the output of the Transformer layer
        a = attn_outputs[0]  # The first part of the output is the result of attention
        # Pass the output through the Adapter layer
        a = self.adapter(a)
        # Returns the modified output (other output remains unchanged)
        outputs = (a,) + attn_outputs[1:]
        return outputs
"""Each GPT2Block contains a series of self-attention (Self-Attention) and feed-forward network (Feed-Forward) layers, which together form the basic architecture of the model."""


