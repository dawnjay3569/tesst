import datetime

dict_orange_portal = [
    'ARTICLE__DESIGNATION_J', 'TYPE_DE_PRODUIT__CODE', 'EXTA__ADRESSE', 'EXTA__N_BPN', 'EXTA_CONSTIT_MLTXMAN', 'ACCES_FIABILISE', 'ACCUEIL_SAV__TEL', 'ACCUEIL_SAV', 'EXTACONSTIT_MLTX_PROVIN', 'EXTA_CONSTIT_MLTX_AFFLU', 'EXTA__CODE_POSTAL', 'DESSERTE_INTERNE_EXT_A', 'DATE_MAD_REELLE_LOCAUX_A', 'DATE_MAD_PREVUE_LOCAUX_A', 'DATE_RDV_FINAL_EN_A', 'DATE_RDV_POC_EN_A', 'EXTA_INTERFACE_OU_NAR', 'EXTA__N_IT', 'EXTA__NOM', 'ARTICLE__NOM', 'EXTA__N_SIRET', 'EXTA__VILLE', 'EXTA__VPVC_DSLAM', 'EXTB__ADRESSE', 'EXTB__N_BPN', 'EXTB_CONSTIT_MLTXMAN', 'EXTBCONSTIT_MLTX_PROVIN', 'EXTB_CONSTIT_MLTX_AFFLU', 'EXTB__CODE_POSTAL', 'VOTRE_REFERENCE', 'DESSERTE_INTERNE_EXT_B', 'DATE_MAD_REELLE_LOCAUX_B', 'DATE_MAD_PREVUE_LOCAUX_B', 'DATE_RDV_FINAL_EN_B', 'DATE_RDV_POC_EN_B', 'EXTB__INTERFACE', 'EXTB__N_IT', 'EXTB__NOM', 'BROCHE', 'EXTB__N_SIRET', 'EXTB__VILLE', 'EXTB__VPVC_CLIENT', 'ARTICLE__CODE', 'CATEGORIE_CC', 'CC_DE_PRODUCTION', 'COMPTE_DE_FACTURATION', 'COMMENTAIRECLIENT', 'N_CONTRAT', 'DATE_DANNULATION', 'DATE_CONVENUE', 'DATE_DEBUT_FACTURATION', 'DEBIT_CC', 'DESSERTE_INTERNE', 'DATE_FIN_FACTURATION', 'DATE_FIN_LIAISON_TEMPO', 'DISTANCEKM', 'DATE_DE_MAD', 'DATE_QUALIFICATION', 'DATE_RDV_FINAL', 'DATE_RECEPTION_COMMANDE', 'DATE_RECEPTION_RESIL', 'DATE_DE_RESILIATION', 'DATE_DE_LAR', 'DATE_DE_LAR__RESIL', 'DATE_SOUHAITEE', 'DUREE_DU_CONTRAT', 'UNITE_DUREE_DU_CONTRAT', 'ETAT_DE_LA_PRESTATION', 'FAS_FRAIS_INSTALLATION', 'MONTANT_GTR', 'NATURE_DE_LOPERATION', 'LOCATION_MENSUELLE', 'TYPE_DE_MODIFICATION', 'MONTANT_DESSERTE_1', 'MONTANT_DESSERTE2', 'MONTANT_LIVRAISEXPRESS', 'MONTANT_OPTION10', 'MONTANT_OPTION11', 'MONTANT_OPTION12', 'MONTANT_OPTION_5', 'MONTANT_OPTION6', 'MONTANT_OPTION7', 'MONTANT_OPTION8', 'MONTANT_OPTION9', 'N_PRESTATION_TECHNIQUE', 'REFERENCE_WEB', 'OPTION_01_GTR', 'OPTION_10', 'OPTION_11', 'OPTION_12', 'OPTION_02_LIVEXPRESS', 'OPTION_03_DESSERTE1', 'OPTION_04_DESSERTE2', 'OPTION_05', 'OPTION_06', 'OPTION_07', 'OPTION_08', 'OPTION_09', 'REPORT_MISE_EN_SERVICE', 'PILOTE_DE_LIVRAISON', 'N_DE_PRESTATION', 'N_PRESTATION_ASSOCIEE', 'N_PRESTATION_ETUDE', 'N_PRESTATION_OPTION_1', 'N_PRESTATION_OPTION_10', 'N_PRESTATION_OPTION_11', 'N_PRESTATION_OPTION_12', 'N_PRESTATION_OPTION_2', 'N_PRESTATION_OPTION_3', 'N_PRESTATION_OPTION_4', 'N_PRESTATION_OPTION_5', 'N_PRESTATION_OPTION_6', 'N_PRESTATION_OPTION_7', 'N_PRESTATION_OPTION_8', 'N_PRESTATION_OPTION_9', 'N_PRESTAT_TETE_PORTE', 'NOM_DU_PROJET', 'VPVC_MIGRATION', 'REMISE_LD', 'SOUS_RESEAU', 'CODE_SRHD', 'NOM_DU_TITULAIRE', 'N_SIREN_DU_TITULAIRE', 'VC4S_VOIE_KLM_', 'ZONE_TARIFAIRE_EXTA', 'ZONE_TARIFAIRE_EXTB', 'DATE_MAJ_COMMERCIALE', 'DATE_MAJ_PILOTAGE', 'TYPE_DE_PRODUIT__NOM', 'SURBOOKING', 'INGENIERIE', 'TYPE_DE_TECHNOLOGIE', 'ALIMENTATION_SECURISEE', 'N_DE_COLLECTE_ASSOCIEE', 'HEBERG_ACCÈS_AU_SERVICE', 'MODE_IMA', 'N_PREST_RSC_RATTACHE', 'GESTION_DE_COS_TDSL', 'OPTION_VLAN', 'RACC_OPT_EXT_A', 'SITE_OPT_RACC_OU_NON', 'TYPE_DE_LIAISON', 'DOUBLE_INTERFACE_USER', 'DESATURATION', 'SYNCHRONISATION', 'ZONAGE_LALPT', 'VLAN_N1_COMMANDE', 'VLAN_N2__COMMANDE', 'VLAN_N3__COMMANDE', 'DEBIT_COLLECTE_REGIONALE', 'DEBIT_COLLECTE_NATIONALE', 'REMOTE_ID', 'REGION_ACCÈS', 'DATE_DETECTION_SATURATIO', 'OPTION_ALIMENTATION', 'ALIMENTATION_SUR_SITE', 'CHANGT_INTERFACE_SITE_A', 'CHANGT_INTERFACE_SITE_B', 'COLOCALISATION_PORTE_', 'COUVERTURE', 'DEPLACEMENT_DEAS', 'INTERFACE_SITE_CENTRAL', 'INTERFACE_SITE_CLIENT', 'N_PREST_LIEN_ABOU_EXT_A', 'N_PREST_LIEN_ABOU_EXT_B', 'N_PREST_RACC_SECURISE', 'DATE_PREVISIONNEL_POI_A', 'DATE_PREVISIONNEL_POI_B', 'NUM_PRESTATION_STM1', 'REGION_RESEAU', 'MODULE_SFP_RESEAU__EAS', 'VLAN1_EN_PRODUCTION', 'DSLAM1_EN_PRODUCTION', 'VLAN2_EN_PRODUCTION', 'DSLAM2_EN_PRODUCTION', 'VLAN3_EN_PRODUCTION', 'DSLAM3_EN_PRODUCTION', 'VLAN4_EN_PRODUCTION_', 'DSLAM4_EN_PRODUCTION_', 'VLAN5_EN_PRODUCTION', 'DSLAM5_EN_PRODUCTION_', 'VLAN6_EN_PRODUCTION___', 'DSLAM6_EN_PRODUCTION', 'DATE_EFFECTIVE_POI_A', 'REFERENCE_DE_LA_DI', 'STATUT_DE_LINTERVENTION', 'DATE_INTERVENTION', 'HEURE_DEBUT_DI', 'HEURE_FIN_DI', 'LIBELLE_DE_RELÈVE', 'CODE_RELÈVE_DI', 'LAST_UPDATED']


def file_loader_decision_maker(filename, final_insert_column, dataframe, workbook_name):
    if str(filename) == "CM_INPUT_FILE":
        finalInsertColumn = final_insert_column
        dataframe['Filename'] = str(workbook_name)
        dataframe['Processed'] = ''
        data = [tuple(x)[1:] for x in dataframe.itertuples()]
        value_placeholder_list = ', '.join(
            [':{0}'.format(x + 1) for x in range(len(finalInsertColumn.split(",")))])
    elif str(filename) == "ZSRM_EV1_DHL":
        del dataframe['Unnamed:_19']
        finalInsertColumn = ','.join(
            ['"' + x + '"' for x in dataframe.columns])
        data = [tuple(x)[1:] for x in dataframe.itertuples()]
        value_placeholder_list = ', '.join(
            [':{0}'.format(x + 1) for x in range(len(finalInsertColumn.split(",")))])
    elif str(filename) == "QUOTE_REQ_LINE_ITEM_RAW":
        del dataframe["Currency Code"]
        del dataframe["Currency Code.1"]
        dataframe['FILENAME'] = "QUOTE_REQ_LINE_ITEM_RAW"
        finalInsertColumn = ','.join(
            ['"' + x + '"' for x in dataframe.columns])
        data = [tuple(x)[1:] for x in dataframe.itertuples()]
        value_placeholder_list = ', '.join(
            [':{0}'.format(x + 1) for x in range(len(finalInsertColumn.split(",")))])
    elif str(filename) == "ASIA_MODCOM":
        finalInsertColumn = final_insert_column
        dataframe['Filename'] = str(workbook_name)
        dataframe['Processed'] = ''
        finalInsertColumn = ','.join(
            ['"' + x + '"' for x in dataframe.columns])
        data = [tuple(x)[1:] for x in dataframe.itertuples()]
        value_placeholder_list = ', '.join(
            [':{0}'.format(x + 1) for x in range(len(finalInsertColumn.split(",")))])
    elif str(filename).upper().startswith('ORANGE_PORTAL'):
        finalInsertColumn = ','.join(
            ['"' + x + '"' for x in dict_orange_portal])
        dataframe['LAST_UPDATED'] = datetime.datetime.now()
        data = [tuple(x)[1:] for x in dataframe.itertuples()]
        value_placeholder_list = ', '.join(
            [':{0}'.format(x + 1) for x in range(len(finalInsertColumn.split(",")))])
    return finalInsertColumn, data, value_placeholder_list