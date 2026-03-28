# Training Data Sanity Check

## 1. status counts
| status               |   count |
|:---------------------|--------:|
| open_set             | 1647112 |
| trainable_core       |  426351 |
| parent_only          |  390760 |
| defer                |   52998 |
| trainable_multilabel |   25781 |

## 2. L1 counts
| level1_label                   |   count |
|:-------------------------------|--------:|
|                                | 1672309 |
| Virion_morphogenesis           |  362774 |
| Genome_maintenance_propagation |  213212 |
| Auxiliary_metabolic_support    |   78130 |
| Host_cell_exit                 |   72438 |
| Gene_expression_reprogramming  |   70803 |
| Host_interface_entry           |   48115 |
| Lifestyle_commitment_switching |   25221 |

## 3. L2 counts
| level2_label                     |   count |
|:---------------------------------|--------:|
|                                  | 1686944 |
| Tail                             |  159679 |
| DNA_recombination                |  111308 |
| DNA_replication                  |   84211 |
| Capsid                           |   80481 |
| Nucleotide_metabolism            |   71973 |
| Head_assembly_packaging          |   60844 |
| Connector_complex                |   60073 |
| Transcription_factor             |   42208 |
| Peptidoglycan_degradation        |   38398 |
| Host_recognition                 |   33680 |
| Membrane_disruption              |   31224 |
| DNA_modification                 |   16267 |
| Phage_transcription_machinery    |   11484 |
| Integration_excision_control     |   11310 |
| Lysogeny_lytic_switch_regulation |   10561 |
| DNA_injection_internal_delivery  |    9306 |
| Host_takeover_interference       |    8703 |
| Protein_RNA_processing           |    6891 |
| Host_cell_exit_broad             |    2722 |
| Host_defense_counterdefense      |    2633 |
| Entry_blocking_exclusion         |    2102 |

## 4. L3 primary counts
| node_primary                         |   count |
|:-------------------------------------|--------:|
|                                      | 1662869 |
| Tail                                 |  103291 |
| DNA_recombination                    |  100979 |
| Nucleotide_metabolism                |   64722 |
| Capsid                               |   48659 |
| Head_tail_connector                  |   40896 |
| Transcription_factor                 |   37206 |
| Tail_fiber                           |   30850 |
| Baseplate                            |   28806 |
| Endolysin                            |   26971 |
| Major_capsid                         |   26245 |
| Helicase                             |   26198 |
| DNA_polymerase                       |   25368 |
| conserved_hypothetical_phage_protein |   21963 |
| Terminase_large                      |   20766 |
| Portal                               |   19177 |
| Holin                                |   15779 |
| putative_membrane_protein            |   15048 |
| DNA_replication                      |   14366 |
| Scaffold_protein                     |   13308 |
| Head_maturation_protease             |   12835 |
| Terminase_small                      |   12715 |
| DNA_methyltransferase                |   12024 |
| Major_tail                           |   11539 |
| RNA_polymerase                       |   10653 |
| Annealing_protein                    |   10316 |
| Primase                              |   10088 |
| Spanin                               |    9487 |
| Host_takeover_interference           |    8703 |
| Cell_wall_depolymerase               |    8411 |
| Tail_tube                            |    8365 |
| Replication_initiator                |    8191 |
| Tail_sheath                          |    7678 |
| Ribonucleotide_reductase             |    7251 |
| Protein_RNA_processing               |    6891 |
| Integrase                            |    6558 |
| CI_like_repressor                    |    6417 |
| Internal_virion_protein              |    5626 |
| Minor_capsid                         |    5577 |
| Transcriptional_activator            |    5002 |
| Excisionase_or_recombinase           |    4752 |
| DNA_modification                     |    4243 |
| Cro_like_regulator                   |    4144 |
| DNA_ejection_protein                 |    3680 |
| Tail_spike                           |    2350 |
| Anti_restriction                     |    2211 |
| Superinfection_exclusion             |    2102 |
| Head_assembly_packaging              |    1220 |
| Host_recognition                     |     480 |
| Anti_CRISPR                          |      26 |

## 5. multilabel counts
| multi_label_flag   |   count |
|:-------------------|--------:|
| no                 | 2517221 |
| yes                |   25781 |

## 6. missing mapping summary
- rows with empty `node_primary`: **1662869**