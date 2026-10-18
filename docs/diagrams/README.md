# Diagrams

The diagrams in the README and in the technical documentation are drawn as [Mermaid](https://mermaid.js.org/)
text files (`*.mmd`) and exported to PNG (`*.png`) so they show in any viewer.

| File | Shows |
|------|-------|
| `architecture` | Browser, nginx, API, engine, domain, AI layer, audit, simulated providers, database |
| `payment-lifecycle` | The payment state machine |
| `safe-approval` | Request approval, MFA step-up, approve, signed webhook, settlement |
| `ai-pipeline` | Policy check, engine facts, masking, model or template, number guard, reply guard |
| `audit-chain` | The hash chain and how Verify finds an edited event |
| `money-flow` | An international transfer through the bank network, hop by hop |
| `national-flow` | A national transfer through a clearing house, with the three rails |

To change one, edit the `.mmd` file and export it again, for example with the Mermaid command line
(this downloads a browser the first time):

```bash
npx -p @mermaid-js/mermaid-cli mmdc -i docs/diagrams/architecture.mmd -o docs/diagrams/architecture.png -s 2 -b white
```

GitHub also draws `.mmd` text that is pasted into a fenced `mermaid` block, if you prefer that.
Every bank, amount and number in these diagrams is synthetic (the money flow uses the sandbox's
worked example: GBP 10,000 through Provider A with charge code OUR).
