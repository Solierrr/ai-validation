# Changelog

## [3.2.0](https://github.com/Solierrr/ai-validation/compare/v3.1.0...v3.2.0) (2026-10-30)


### Features

* add the local run commands ([4d1eb6e](https://github.com/Solierrr/ai-validation/commit/4d1eb6eafa4640cd7910f2b4d5896f96ba3f8a73))
* adopt the openapi, error, version and health standards ([#46](https://github.com/Solierrr/ai-validation/issues/46)) ([4278e58](https://github.com/Solierrr/ai-validation/commit/4278e580f2cfa88afac5137e5ac1ce64e53eeff4))
* debug endpoint ([#45](https://github.com/Solierrr/ai-validation/issues/45)) ([10ce1d9](https://github.com/Solierrr/ai-validation/commit/10ce1d9bd57b66c7f85b58d43c9c551ba53c62e5))
* read the llm keys from the environment and add openai ([#41](https://github.com/Solierrr/ai-validation/issues/41)) ([aeb6a14](https://github.com/Solierrr/ai-validation/commit/aeb6a14afa6759c53d348a03c8f71130d82d3e16))
* restrict cors and require a token on the validation routes ([#50](https://github.com/Solierrr/ai-validation/issues/50)) ([bd8e1f7](https://github.com/Solierrr/ai-validation/commit/bd8e1f77393edad72ab48a125694a2990b2e9460))
* run a single node with edited prompts in the certificates and cnpj debug routes ([#48](https://github.com/Solierrr/ai-validation/issues/48)) ([a4acf9b](https://github.com/Solierrr/ai-validation/commit/a4acf9bb9bdea68d010b756238dc5d015ca8120b))
* show the tool calls and the available tools in the debug ([#51](https://github.com/Solierrr/ai-validation/issues/51)) ([7855fc9](https://github.com/Solierrr/ai-validation/commit/7855fc9f3b7d90a2e52ffa9eba74508a075b7292))

## [3.1.0](https://github.com/Solierrr/ai-validation/compare/v3.0.0...v3.1.0) (2026-09-30)


### Features

* add real merge checkbox for qa sync and guard bot self-trigger ([a458196](https://github.com/Solierrr/ai-validation/commit/a458196ae31301e42888d3197b0ac9218ac97ffb))
* improve automated pr comments and add pr welcome workflow ([53d4312](https://github.com/Solierrr/ai-validation/commit/53d43121d63872b93aab325584f73347ba353c82))
* link to existing sync pr in the initial checkbox comment ([c53f762](https://github.com/Solierrr/ai-validation/commit/c53f762666990be3f5b9f0b6770af411ea434e1b))


### Bug Fixes

* add blank line before release-please separator and use full pull request wording ([ce3a8f5](https://github.com/Solierrr/ai-validation/commit/ce3a8f524f4ef6a8870285998ef01fedea2629cb))
* grant pull-requests write permission to release workflow ([3b8f9b5](https://github.com/Solierrr/ai-validation/commit/3b8f9b5ecf9d11b24bf83aed16c269b5d43713ac))
* pass vault arguments correctly in PowerShell ([b9b85da](https://github.com/Solierrr/ai-validation/commit/b9b85daaa52411f07ce021dd16829606514d9e83))
* support current infisical cli repository ([2c44ac2](https://github.com/Solierrr/ai-validation/commit/2c44ac2907591b379a478f027afc6320087c6c50))
* support powershell secret extraction ([aa1e493](https://github.com/Solierrr/ai-validation/commit/aa1e493a0f3d2f15338931ad9c88935dc87c6193))

## [3.0.0](https://github.com/Solierrr/ai-validation/compare/v0.1.0...v3.0.0) (2026-09-24)


### Features

* adding __init__ in directorys and solving requirements ([aaaddc3](https://github.com/Solierrr/ai-validation/commit/aaaddc32a601a2d8226833e24d5114ba2ff81ae0))
* adding pr template and workflows ([46c4f77](https://github.com/Solierrr/ai-validation/commit/46c4f7750b77bfb1a8439a65c4e04b9a6d7cdbd1))
* publish docker image on push to main ([4e64673](https://github.com/Solierrr/ai-validation/commit/4e6467384da96726b5d4cea4ec3365c3893b17f4))
* publish docker image to docker hub on push to main ([d009204](https://github.com/Solierrr/ai-validation/commit/d00920400ab66709b0098fe0b59ac6cc9e782375))
* sign-in-technical-and-company ([48498a1](https://github.com/Solierrr/ai-validation/commit/48498a17ecf927181a32b18c1da767aaf18252b6))
* wire up qa-sync and repo-cleanup reusable workflows ([3ad1173](https://github.com/Solierrr/ai-validation/commit/3ad1173242efccace37b020cc4cb6833c7c20dfb))
* wire up qa-sync and repo-cleanup reusable workflows ([81c70b8](https://github.com/Solierrr/ai-validation/commit/81c70b81c4b93466d0f1e152072939710304dd6d))


### Bug Fixes

* add missing CMD to start the FastAPI server ([62e2257](https://github.com/Solierrr/ai-validation/commit/62e22572e55ce0d446561b6fe202b058d668b316))
* add missing runtime and test dependencies to requirements.txt ([48080e7](https://github.com/Solierrr/ai-validation/commit/48080e7bce82352793b90101bb6c0e2eb137726a))
* trigger releases by command ([dcad882](https://github.com/Solierrr/ai-validation/commit/dcad882166d91bcd32858c2168037c6751627c0c))
