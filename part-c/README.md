# Part C - Salesforce Integration Design

## Overview

Loan officers work from the Salesforce Opportunity record page, so the credit risk score should appear directly there without opening another tool. The Salesforce integration will call the AWS-hosted FastAPI credit risk API from Part B through API Gateway, using the Part A `/predict` endpoint for real-time scoring and `/predict/batch` for campaign queues.

## Q1 - How Salesforce Calls the AWS API

Use a **Lightning Web Component (LWC)** on the Opportunity Lightning Record Page. When the record page opens, the LWC calls an Apex controller method. Apex reads the Opportunity fields, derives FOIR and LTV, calls API Gateway `/predict`, parses the API response, updates the Opportunity result fields, and returns the score to the LWC for display.

Authentication is handled with a Salesforce **Named Credential** backed by an **External Credential**. Apex calls a logical endpoint such as `callout:NiwasCreditRiskApi/predict`, so API keys, OAuth tokens, or JWT credentials are not hardcoded in Apex.

Flow sketch:

```text
Opportunity page opens
  -> LWC connectedCallback loads recordId
  -> Apex CreditRiskController.scoreOpportunity(recordId)
  -> Apex derives foir, ltv, bureau_score
  -> Apex HTTP POST to API Gateway /predict via Named Credential
  -> FastAPI returns risk_label, probability, model_version, timestamp
  -> Apex updates Opportunity credit risk fields
  -> LWC refreshes badge and score on the page
```

Pseudocode:

```apex
Opportunity opp = [
    SELECT Monthly_EMI_Obligation__c, Monthly_Income__c,
           Loan_Amount__c, Property_Value__c, Bureau_Score__c
    FROM Opportunity
    WHERE Id = :opportunityId
];

Decimal foir = opp.Monthly_EMI_Obligation__c / opp.Monthly_Income__c;
Decimal ltv = opp.Loan_Amount__c / opp.Property_Value__c;

HttpRequest req = new HttpRequest();
req.setEndpoint('callout:NiwasCreditRiskApi/predict');
req.setMethod('POST');
req.setHeader('Content-Type', 'application/json');
req.setTimeout(3000);
req.setBody(JSON.serialize(new Map<String, Object>{
    'applicant_id' => String.valueOf(opp.Id),
    'foir' => foir,
    'ltv' => ltv,
    'bureau_score' => opp.Bureau_Score__c
}));

HttpResponse res = new Http().send(req);
// Parse response, update Opportunity fields, return display result to LWC.
```

## Q2 - Data Mapping

**The FOIR and LTV calculations should happen in Salesforce before the API call. This keeps the API contract simple and makes the business derivation visible to Salesforce admins.**

| Salesforce field | API field | Logic |
| --- | --- | --- |
| `Monthly_EMI_Obligation__c` | `foir` | `Monthly_EMI_Obligation__c / Monthly_Income__c` |
| `Loan_Amount__c` | `ltv` | `Loan_Amount__c / Property_Value__c` |
| `Bureau_Score__c` | `bureau_score` | Direct mapping |
| `Monthly_Income__c` | none | Denominator for FOIR |
| `Property_Value__c` | none | Denominator for LTV |

If `Monthly_Income__c` or `Property_Value__c` is null or zero, Apex should skip the API call. It should write a clear message to `Credit_Risk_Error__c`, set the UI state to `Insufficient data for risk score`, and avoid sending invalid values to the API. The same handling applies when bureau score is missing or outside the API's accepted range.

## Q3 - Showing Results to the Loan Officer

Store the result on the Opportunity so the score is visible, reportable, and auditable:

| Field | Type | Purpose |
| --- | --- | --- |
| `Credit_Risk_Label__c` | Picklist or Text | `LOW`, `MEDIUM`, `HIGH` |
| `Credit_Risk_Probability__c` | Percent or Number | API probability value |
| `Credit_Risk_Model_Version__c` | Text | Active model version, for example `v1.0` |
| `Credit_Risk_Last_Scored_At__c` | DateTime | API response timestamp or Salesforce update time |
| `Credit_Risk_Error__c` | Long Text Area | Last integration or validation error |

The LWC should display a compact badge on the record page: green for `LOW`, amber for `MEDIUM`, and red for `HIGH`. It can also show the probability and model version below the badge.

If the API fails or times out, the loan officer should see a non-blocking message such as `Credit risk score unavailable. Showing last saved score.` If a previous score exists, keep showing it with the last scored timestamp. Apex should write the failure message to `Credit_Risk_Error__c` and avoid clearing the previous valid result.

## Q4 - Security and Governance

The API Gateway endpoint is public HTTPS, but prediction endpoints must not be anonymous. Salesforce should call it through **Named Credential + External Credential**, using OAuth/JWT authorization or a tightly controlled API key issued only for Salesforce. API Gateway should enforce an authorizer or usage plan, and AWS should use WAF/rate limiting where appropriate.

On AWS, Lambda should use a least-privilege IAM role. It should only read the active S3 model path, read required secrets from Secrets Manager, and write logs to CloudWatch. CloudWatch logs and alarms provide an audit trail for call volume, errors, latency, and rollback triggers. Use separate credentials for Salesforce and internal analytics so access can be revoked independently.

FOIR, LTV, and bureau score are sensitive borrower data. For Niwas HFC, the AWS API, Lambda, S3 model bucket, CloudWatch logs, and Secrets Manager secrets should be deployed in **Asia Pacific Mumbai (`ap-south-1`)** so borrower data remains in India and supports RBI/NBFC/HFC data-localisation expectations. Logs should avoid unnecessary borrower identifiers beyond the minimum needed for operational tracing.

## Bonus - Campaign Batch Processing

For a campaign queue, such as 200 new leads or Opportunities uploaded from a CSV, use **Batch Apex** or **Queueable Apex**. Salesforce should process records in chunks of up to 50 because the Part A `/predict/batch` endpoint accepts a maximum of 50 applications.

Batch flow:

```text
CSV import creates Leads/Opportunities
  -> Flow, scheduled job, or campaign status change starts Batch Apex
  -> Batch Apex queries eligible records
  -> Each execute chunk maps up to 50 records into /predict/batch request
  -> API returns predictions list and summary
  -> Apex updates successful records
  -> Apex logs failed records for retry or manual review
```

Partial failures should not block successful predictions. If 3 out of 200 records fail validation or timeout, Salesforce should update the 197 successful records, mark the 3 failed records with `Credit_Risk_Error__c`, and retry them once through a Queueable job. If they fail again, route them to an operations queue or report for manual review.
