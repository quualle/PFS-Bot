"""
Direkter Test für BigQuery-Abfrage mit minimalen Abhängigkeiten.
"""
import os
import json
from google.cloud import bigquery

def main():
    """Hauptfunktion, die BigQuery direkt testet."""
    print("Direkter Test für BigQuery")
    
    # Seller ID für Abfrage
    seller_id = "62d00b56a384fd908f7f5a6c"  # Marco's ID
    
    # 1. Einfache Authentifizierung testen
    print("1. Authentifizierung testen...")
    try:
        # Verwende Standardauthentifizierung (Application Default Credentials)
        client = bigquery.Client()
        print(f"Erfolgreiche Authentifizierung als: {client.project}")
    except Exception as e:
        print(f"Fehler bei Authentifizierung: {e}")
        return
    
    # 2. Einfache Abfrage testen
    print("2. Einfache Abfrage testen...")
    try:
        query = "SELECT 1 as test"
        query_job = client.query(query)
        results = query_job.result()
        
        for row in results:
            print(f"Einfache Abfrage erfolgreich: {row.test}")
    except Exception as e:
        print(f"Fehler bei einfacher Abfrage: {e}")
        return
    
    # 3. Reale Abfrage für paused customers testen
    print("3. Abfrage für Kunden in Pause testen...")
    try:
        # Vereinfachte Abfrage
        query = """
        WITH active_contracts AS (
          SELECT c._id AS contract_id
          FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
          WHERE l.seller_id = @seller_id AND c.archived = 'false'
        ),
        has_previous_care_stays AS (
          SELECT c.contract_id
          FROM active_contracts c
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
          WHERE cs.stage = 'Bestätigt' AND DATE(TIMESTAMP(cs.arrival)) < CURRENT_DATE()
        ),
        current_care_stays AS (
          SELECT c.contract_id
          FROM active_contracts c
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
          WHERE cs.stage = 'Bestätigt' AND DATE(TIMESTAMP(cs.arrival)) <= CURRENT_DATE() AND DATE(TIMESTAMP(cs.departure)) >= CURRENT_DATE()
        )
        SELECT COUNT(*) AS total_paused
        FROM has_previous_care_stays hpcs
        WHERE hpcs.contract_id NOT IN (SELECT contract_id FROM current_care_stays)
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        for row in results:
            print(f"Kunden in Pause: {row.total_paused}")
            
    except Exception as e:
        print(f"Fehler bei Kunden in Pause Abfrage: {e}")
        return
    
    # 4. Vollständige Abfrage mit Detaildaten testen
    print("4. Vollständige Abfrage mit Details testen...")
    try:
        # Vollständige Abfrage
        query = """
        WITH active_contracts AS (
          SELECT 
            c._id AS contract_id,
            c.created_at,
            h.lead_id,
            lead_names.first_name,
            lead_names.last_name,
            agencies.name AS agency_name
          FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
          LEFT JOIN `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_names ON l._id = lead_names._id
          LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.agencies` AS agencies ON c.agency_id = agencies._id
          WHERE l.seller_id = @seller_id AND c.archived = 'false'
        ),
        has_previous_care_stays AS (
          SELECT 
            c.contract_id,
            MAX(cs.departure) AS last_departure
          FROM active_contracts c
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
          WHERE cs.stage = 'Bestätigt' AND DATE(TIMESTAMP(cs.arrival)) < CURRENT_DATE()
          GROUP BY c.contract_id
        ),
        current_care_stays AS (
          SELECT 
            c.contract_id
          FROM active_contracts c
          JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
          WHERE cs.stage = 'Bestätigt' AND DATE(TIMESTAMP(cs.arrival)) <= CURRENT_DATE() AND DATE(TIMESTAMP(cs.departure)) >= CURRENT_DATE()
        ),
        next_care_stays AS (
          SELECT 
            contract_id,
            next_arrival,
            next_stage
          FROM (
            SELECT 
              c.contract_id,
              cs.arrival AS next_arrival,
              cs.stage AS next_stage,
              ROW_NUMBER() OVER (PARTITION BY c.contract_id ORDER BY cs.arrival) AS rn
            FROM active_contracts c
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
            WHERE DATE(TIMESTAMP(cs.arrival)) > CURRENT_DATE()
          ) 
          WHERE rn = 1
        )
        SELECT 
          ac.contract_id,
          ac.first_name,
          ac.last_name,
          ac.agency_name,
          hpcs.last_departure,
          DATE_DIFF(CURRENT_DATE(), DATE(TIMESTAMP(hpcs.last_departure)), DAY) AS days_on_pause,
          ncs.next_arrival AS naechster_carestay,
          ncs.next_stage AS status_naechster_carestay,
          (
            SELECT COUNT(*) 
            FROM has_previous_care_stays hpcs2
            WHERE hpcs2.contract_id NOT IN (SELECT contract_id FROM current_care_stays)
              AND hpcs2.last_departure IS NOT NULL
          ) AS total_paused_customers
        FROM active_contracts ac
        JOIN has_previous_care_stays hpcs ON ac.contract_id = hpcs.contract_id
        LEFT JOIN next_care_stays ncs ON ac.contract_id = ncs.contract_id
        WHERE ac.contract_id NOT IN (SELECT contract_id FROM current_care_stays)
          AND hpcs.last_departure IS NOT NULL
        ORDER BY days_on_pause DESC
        LIMIT 1000
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        row_count = 0
        for row in results:
            row_count += 1
            if row_count == 1:
                print(f"Erster Kunde: {row.first_name} {row.last_name}")
                print(f"Gesamtzahl der Kunden in Pause: {row.total_paused_customers}")
        
        print(f"Insgesamt gefundene Kunden: {row_count}")
            
    except Exception as e:
        print(f"Fehler bei vollständiger Abfrage: {e}")
        import traceback
        traceback.print_exc()
        return
    
if __name__ == "__main__":
    main() 