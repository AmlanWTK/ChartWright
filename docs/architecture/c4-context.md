# C4 Level 1 — System Context

Shows Chartwright as a single system and the people and external systems it interacts with.

```mermaid
graph TB
    subgraph Users
      REV["Reviewer / PA coordinator"]
      ADM["RCM ops / admin"]
      DEV["Integrator / developer"]
    end

    subgraph Sources["Document sources"]
      FAX["Fax / email gateway"]
      EHR["EHR (FHIR DocumentReference)"]
      SFTP["Batch SFTP drop"]
      API["REST API clients"]
    end

    CW["Chartwright<br/>Clinical Document Intelligence Platform"]

    subgraph External["External systems"]
      PAYER["Payer PA / FHIR APIs"]
      MODELS["Model providers<br/>(self-hosted VLMs + frontier APIs)"]
      POLICY["Payer policy sources +<br/>code systems (ICD-10/CPT/NPI)"]
    end

    FAX --> CW
    EHR --> CW
    SFTP --> CW
    API --> CW

    REV <--> CW
    ADM --> CW
    DEV --> CW

    CW --> PAYER
    CW <--> MODELS
    CW <--> POLICY

    CW -->|FHIR resources + webhooks| API
```

**Reading:** documents enter from multiple channels; reviewers and admins interact via the web app; the platform calls model providers and policy/code sources, and emits FHIR-aligned results to payers and integrators (aligned to CMS-0057-F).
