## 🏷️ Complete Manufacturer-Exact Lifecycle Status Terminology Registry

Industrial automation, embedded IoT silicon, and enterprise IT hardware manufacturers **do not adhere to a single unified status vocabulary**. Each vendor defines rigorous proprietary lifecycle phases governing purchasing windows, warranty maintenance, component repair, and obsolescence.

> [!IMPORTANT]
> **Zero Dropped EOL Records Rule**: Products that have reached End of Life (EOL), Discontinued, Phase-Out, or Obsolete status **always produce an entry even if the vendor does not publish an explicit milestone date**. Missing dates will NEVER drop a record. The extractor and storage preserve all end-of-life models, tagging missing dates cleanly in metadata.

Below is the comprehensive cross-vendor status terminology catalog across **all 140 supported enterprise vendors**:

### 1. Operational Technology (OT) - Industrial Automation & Control (54 Supported Vendors)

| Vendor / Manufacturer | Official Lifecycle Phasing Model | Exact Vendor Status Terminology | Operational Definition & Impact |
|:---|:---|:---|:---|
| **ABB** (abb) | 4-Phase Model (Active, Classic, Limited, Obsolete) | `Active` | Full range of lifecycle services and active series production for new installations. |
| **ABB** (abb) | 4-Phase Model (Active, Classic, Limited, Obsolete) | `Classic` | Enhanced services available; product is mature and successor product is actively recommended for new lines. |
| **ABB** (abb) | 4-Phase Model (Active, Classic, Limited, Obsolete) | `Limited` | Manufacturing stopped. Services limited to spare parts, workshop repair, and technical advice. |
| **ABB** (abb) | 4-Phase Model (Active, Classic, Limited, Obsolete) | `Obsolete` | End of lifecycle. Spares exhausted; support provided on best-effort basis only. Urgent replacement required. |
| **Advantech** (advantech) | Industrial IPC & Automation EOL | `Phase-In / Active` | Regular volume shipment. |
| **Advantech** (advantech) | Industrial IPC & Automation EOL | `Phase-Out (LTB / LTS)` | Last-Time-Buy and Last-Time-Ship deadlines published. |
| **Advantech** (advantech) | Industrial IPC & Automation EOL | `End of Life (EOL)` | Part retired; warranty repairs only. |
| **B&R Industrial Automation** (br_automation) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Banner Engineering** (banner_engineering) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Baumuller** (baumuller) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Beckhoff Automation** (beckhoff) | TwinCAT & PC-Control Lifecycle | `Available` | Standard catalog series available for new systems. |
| **Beckhoff Automation** (beckhoff) | TwinCAT & PC-Control Lifecycle | `Phase-Out (Auslauf)` | Successor released; component available for fixed transition window. |
| **Beckhoff Automation** (beckhoff) | TwinCAT & PC-Control Lifecycle | `Discontinued (Abgekündigt)` | Orderable only as replacement/service spare part. |
| **Beckhoff Automation** (beckhoff) | TwinCAT & PC-Control Lifecycle | `End of Service` | Obsolescence reached; repair subject to component availability. |
| **Bosch** (bosch) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Danfoss Drives** (danfoss) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Delta Electronics** (delta_electronics) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Dragos Industrial Cybersecurity** (dragos) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Eaton Electrical** (eaton) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Emerson Electric** (emerson) | DeltaV / Ovation / PACSystems Lifecycle | `Available` | Active production and standard customer delivery. |
| **Emerson Electric** (emerson) | DeltaV / Ovation / PACSystems Lifecycle | `Extended Support` | Mature system; replacement series released. |
| **Emerson Electric** (emerson) | DeltaV / Ovation / PACSystems Lifecycle | `Retired` | Manufacturing concluded; support on spare parts availability. |
| **Endress+Hauser** (endress_hauser) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **FANUC Corporation** (fanuc) | CNC & Robotics Lifetime Support | `Current Production` | Active controller and drive manufacturing. |
| **FANUC Corporation** (fanuc) | CNC & Robotics Lifetime Support | `Discontinued` | Production stopped; lifelong repair service supported. |
| **FANUC Corporation** (fanuc) | CNC & Robotics Lifetime Support | `Maintenance Limited` | Repairs dependent on component stock. |
| **Festo SE & Co. KG** (festo) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Fuji Electric** (fuji_electric) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **GE Vernova / GE Digital** (ge_digital) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **HMS Networks** (hms_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Hans Turck GmbH** (turck) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Hirschmann (Belden)** (hirschmann) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Hitachi** (hitachi) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Honeywell** (honeywell) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **IDEC Corporation** (idec) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **JTEKT Toyoda** (toyoda) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Keyence Corporation** (keyence) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Kuka Robotics** (kuka) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Lenze** (lenze) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Mitsubishi Electric** (mitsubishi) | Production to Repair Termination (7-Year Maintenance) | `Active / Current Production` | Standard series catalog offering. |
| **Mitsubishi Electric** (mitsubishi) | Production to Repair Termination (7-Year Maintenance) | `Discontinuation Announced` | Technical bulletin published with Last Time Buy deadline and successor model. |
| **Mitsubishi Electric** (mitsubishi) | Production to Repair Termination (7-Year Maintenance) | `Discontinued (製造中止 / 生産終了)` | Production ended; new equipment orders no longer accepted. |
| **Mitsubishi Electric** (mitsubishi) | Production to Repair Termination (7-Year Maintenance) | `Repair Termination (修理対応終了)` | 7-year spare parts supply and workshop repair service period concluded. |
| **Moog Industrial** (moog) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Moxa Technologies** (moxa) | Industrial Networking Lifecycle | `Active` | Active network switch, router, or serial gateway. |
| **Moxa Technologies** (moxa) | Industrial Networking Lifecycle | `Phase-Out Announced` | Last-time buy date communicated. |
| **Moxa Technologies** (moxa) | Industrial Networking Lifecycle | `Discontinued (EOL)` | Product line retired; replacement model designated. |
| **National Instruments** (national_instruments) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Nidec Control Techniques** (nidec_control_techniques) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Omron Corporation** (omron) | Manufacturing to Maintenance Transition Lifecycle | `Active Production` | Standard catalog model in volume production. |
| **Omron Corporation** (omron) | Manufacturing to Maintenance Transition Lifecycle | `Production Discontinuation Announced (生産終了予告)` | Formal circular issued communicating the final order deadline (Last Time Buy). |
| **Omron Corporation** (omron) | Manufacturing to Maintenance Transition Lifecycle | `Discontinued (生産終了 / 製造中止)` | Factory production has permanently terminated. |
| **Omron Corporation** (omron) | Manufacturing to Maintenance Transition Lifecycle | `Maintenance / Repair Termination (修理対応終了)` | 7-year post-discontinuation repair window expired; maintenance support ceased. |
| **Panasonic** (panasonic) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Parker Hannifin** (parker_hannifin) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Pepperl+Fuchs** (pepperl_fuchs) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Phoenix Contact** (phoenix_contact) | Standard to Auslaufartikel | `Standard Article` | Full availability and standard series production. |
| **Phoenix Contact** (phoenix_contact) | Standard to Auslaufartikel | `Discontinued Item (Auslaufartikel)` | Notification issued with final ordering deadline and designated successor. |
| **Phoenix Contact** (phoenix_contact) | Standard to Auslaufartikel | `Discontinued` | Production ceased; replacement article assigned. |
| **Pilz Automation Safety** (pilz) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Pro-face** (pro_face) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Red Lion Controls** (red_lion) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Rockwell Automation (Allen-Bradley)** (rockwell_automation) | 4-Phase Lifecycle (Active, Active Mature, End of Life, Discontinued) | `Active` | Most current hardware/software offering within a product category; fully available for new designs. |
| **Rockwell Automation (Allen-Bradley)** (rockwell_automation) | 4-Phase Lifecycle (Active, Active Mature, End of Life, Discontinued) | `Active Mature` | Product is actively manufactured and supported, but a newer generation or migration target exists. |
| **Rockwell Automation (Allen-Bradley)** (rockwell_automation) | 4-Phase Lifecycle (Active, Active Mature, End of Life, Discontinued) | `End of Life` | Discontinuation date announced. Final orders accepted until published Last Time Buy (LTB) date. |
| **Rockwell Automation (Allen-Bradley)** (rockwell_automation) | 4-Phase Lifecycle (Active, Active Mature, End of Life, Discontinued) | `Discontinued` | No longer manufactured. Repair services, remanufactured parts, and technical assistance available while parts inventory lasts. |
| **SICK Sensor Intelligence** (sick) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **SMC Corporation** (smc) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Schneider Electric** (schneider_electric) | Multi-Phase Commercial & Support Timeline | `Commercialised` | Active commercial product available for quotes, orders, and routine warranty maintenance. |
| **Schneider Electric** (schneider_electric) | Multi-Phase Commercial & Support Timeline | `End of Commercialisation (EoC)` | Commercial sales window closed; final deliveries executed. Corresponds to Last Time Buy. |
| **Schneider Electric** (schneider_electric) | Multi-Phase Commercial & Support Timeline | `End of Standard Support` | Standard software/firmware bug fixes, driver releases, and routine technical phone support expire. |
| **Schneider Electric** (schneider_electric) | Multi-Phase Commercial & Support Timeline | `End of Extended Support / Obsolescence` | No repairs, spare parts, or hardware warranty available. Migration to modern platform required. |
| **Shibaura Machine (Toshiba Machine)** (shibaura_machine) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Siemens** (siemens) | 4-Stage Milestone Lifecycle (Lieferfreigabe to Lieferstopp) | `Delivery Release (Lieferfreigabe)` | Official market launch; volume series production and active ordering. |
| **Siemens** (siemens) | 4-Stage Milestone Lifecycle (Lieferfreigabe to Lieferstopp) | `Phase-Out Product (Auslauftyp / Auslaufphase)` | Active phase-out notice issued. Product remains orderable as new for standard 1 to 2 years while migration begins. |
| **Siemens** (siemens) | 4-Stage Milestone Lifecycle (Lieferfreigabe to Lieferstopp) | `Product Cancellation (Produktabkündigung)` | Active production stopped. Parts supplied primarily as spare parts (Ersatzteil); engineering updates frozen. |
| **Siemens** (siemens) | 4-Stage Milestone Lifecycle (Lieferfreigabe to Lieferstopp) | `Product Discontinuation (Lieferstopp / Einstellung der Ersatzteilieferung)` | Complete discontinuation. Spare part deliveries and manufacturer repairs terminated; legacy obsolescence. |
| **Unitronics** (unitronics) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Valmet Automation** (valmet) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **WAGO Kontakttechnik** (wago) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Weidmuller Interface** (weidmuller) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Yamaha Motor Robotics** (yamaha) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Yaskawa Electric** (yaskawa) | Motoman & Inverter Lifecycle | `Standard Production` | Active drive and servo series. |
| **Yaskawa Electric** (yaskawa) | Motoman & Inverter Lifecycle | `Production Discontinuation` | Final order window communicated. |
| **Yaskawa Electric** (yaskawa) | Motoman & Inverter Lifecycle | `Support Period Expired` | Parts exhausted; replacement required. |
| **Yokogawa Electric** (yokogawa) | CENTUM & ProSafe-RS Lifecycle Support | `Current Product` | Active DCS/PLC hardware in active distribution. |
| **Yokogawa Electric** (yokogawa) | CENTUM & ProSafe-RS Lifecycle Support | `Phased Out (LTB)` | Last Time Buy notice communicated; order cutoff specified. |
| **Yokogawa Electric** (yokogawa) | CENTUM & ProSafe-RS Lifecycle Support | `Discontinued / Obsolete` | Mainstream support concluded; long-term service contract only. |
| **ifm electronic** (ifm_electronic) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |

### 2. Internet of Things (IoT) - Embedded Silicon & Connected Hardware (44 Supported Vendors)

| Vendor / Manufacturer | Official Lifecycle Phasing Model | Exact Vendor Status Terminology | Operational Definition & Impact |
|:---|:---|:---|:---|
| **Arduino Pro & IoT** (arduino) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Avigilon (Motorola Solutions)** (avigilon) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Axis Communications** (axis_communications) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Basler AG** (basler) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Cognex Corporation** (cognex) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Dahua Technology** (dahua) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Digi International** (digi_intl) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Dragino Technology** (dragino) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Espressif Systems** (espressif) | ESP32/ESP8266 Longevity Policy | `Mass Production` | In volume production with active ESP-IDF support. |
| **Espressif Systems** (espressif) | ESP32/ESP8266 Longevity Policy | `End of Life (EOL)` | Production cessation announced with 6-month LTB. |
| **Eurotech Edge Gateway** (eurotech) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Hanwha Vision** (hanwha_vision) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Hikvision Digital Technology** (hikvision) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Intel Corporation** (intel) | Product Discontinuation Notice (PDN) Workflow | `Launched` | Volume production silicon and embedded processors. |
| **Intel Corporation** (intel) | Product Discontinuation Notice (PDN) Workflow | `Product Discontinuation Notice (PDN)` | Formal notification of impending lifecycle termination. |
| **Intel Corporation** (intel) | Product Discontinuation Notice (PDN) Workflow | `Last Time Buy (LTB)` | Final date for non-cancellable, non-returnable purchase orders. |
| **Intel Corporation** (intel) | Product Discontinuation Notice (PDN) Workflow | `Last Time Ship (LTS)` | Final date for factory delivery and dispatch. |
| **Intel Corporation** (intel) | Product Discontinuation Notice (PDN) Workflow | `End of Interactive Support (EOIS)` | Online technical assistance, errata updates, and microcode patches frozen. |
| **Kerlink LoRaWAN** (kerlink) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Kontron Embedded** (kontron) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Kyocera AVX** (kyocera) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Laird Connectivity** (laird_connect) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Libelium IoT** (libelium) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Microchip Technology** (microchip) | Client-Driven Obsolescence Practice | `In Production` | Standard volume availability. |
| **Microchip Technology** (microchip) | Client-Driven Obsolescence Practice | `At Risk` | Supply chain warning; alternative pinout advised. |
| **Microchip Technology** (microchip) | Client-Driven Obsolescence Practice | `Discontinued` | EOL notice completed. |
| **Milesight** (milesight) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Mobotix AG** (mobotix) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **MultiTech Systems** (multitech) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Murata Manufacturing** (murata) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **NXP Semiconductors** (nxp) | Longevity Program & Discontinuation | `Active (10/15 Year Longevity)` | Guaranteed long-term supply availability. |
| **NXP Semiconductors** (nxp) | Longevity Program & Discontinuation | `End of Life (EOL) Announced` | Discontinuation schedule published with LTB date. |
| **NXP Semiconductors** (nxp) | Longevity Program & Discontinuation | `Discontinued` | Part number retired. |
| **Nordic Semiconductor** (nordic_semi) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Nozomi Networks** (nozomi_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Particle Industries** (particle) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Qualcomm** (qualcomm) | Cellular & SoC Lifecycle | `Active` | Active modem / SoC shipment. |
| **Qualcomm** (qualcomm) | Cellular & SoC Lifecycle | `End of Life (EOL)` | Silicon revision retired; firmware SDK frozen. |
| **Quectel Wireless Solutions** (quectel) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Raspberry Pi Ltd** (raspberry_pi) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **STMicroelectronics** (stmicroelectronics) | 10-Year Longevity Commitment | `Active` | Recommended for new designs; standard production. |
| **STMicroelectronics** (stmicroelectronics) | 10-Year Longevity Commitment | `NRND` | Mature silicon; migration path provided. |
| **STMicroelectronics** (stmicroelectronics) | 10-Year Longevity Commitment | `Discontinued` | Fabrication ended after last-time buy window. |
| **Seeed Studio Industrial** (seeed_studio) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Semtech** (semtech) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Sensirion Environmental** (sensirion) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Silicon Laboratories** (silicon_labs) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Sony Professional** (sony) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Teledyne FLIR** (flir) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Telit Cinterion** (telit) | Cellular IoT Module Lifecycle | `Active` | Current cellular IoT module. |
| **Telit Cinterion** (telit) | Cellular IoT Module Lifecycle | `Last Time Buy (LTB)` | Order cutoff for 2G/3G/LTE Cat-1 modules. |
| **Telit Cinterion** (telit) | Cellular IoT Module Lifecycle | `End of Maintenance` | AT firmware patches concluded. |
| **Teltonika Networks** (teltonika) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Texas Instruments** (texas_instruments) | Semiconductor Product Lifecycle | `Active` | In volume production and recommended for new designs. |
| **Texas Instruments** (texas_instruments) | Semiconductor Product Lifecycle | `Not Recommended for New Designs (NRND)` | Existing customers supported, but newer pin-compatible silicon advised. |
| **Texas Instruments** (texas_instruments) | Semiconductor Product Lifecycle | `Last Time Buy (LTB)` | Final order placement deadline before wafer fab shutdown. |
| **Texas Instruments** (texas_instruments) | Semiconductor Product Lifecycle | `Obsolete / Discontinued` | Device retired; no longer manufactured or orderable. |
| **Uniview Technologies** (uniview) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Verkada** (verkada) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Zebra Technologies** (zebra) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **u-blox** (ublox) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |

### 3. Enterprise IT & Networking - Infrastructure & Datacenter Systems (42 Supported Vendors)

| Vendor / Manufacturer | Official Lifecycle Phasing Model | Exact Vendor Status Terminology | Operational Definition & Impact |
|:---|:---|:---|:---|
| **Alcatel-Lucent Enterprise** (alcatel_lucent_enterprise) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Allied Telesis** (allied_telesis) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Arista Networks** (arista) | EOS & Switch Lifecycle | `Active` | Regular production switch. |
| **Arista Networks** (arista) | EOS & Switch Lifecycle | `End of Sale` | Commercial cutoff. |
| **Arista Networks** (arista) | EOS & Switch Lifecycle | `End of Software Maintenance` | EOS updates frozen. |
| **Arista Networks** (arista) | EOS & Switch Lifecycle | `End of Service Contract` | Hardware support ceases. |
| **Barracuda Networks** (barracuda_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Canonical** (canonical) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Check Point Software** (check_point) | Appliance & Gaia OS Lifecycle | `Current Product` | Active gateway. |
| **Check Point Software** (check_point) | Appliance & Gaia OS Lifecycle | `End of Sale` | Sales conclude. |
| **Check Point Software** (check_point) | Appliance & Gaia OS Lifecycle | `End of Engineering Support` | Hotfix freeze. |
| **Check Point Software** (check_point) | Appliance & Gaia OS Lifecycle | `End of Support` | Complete contract end. |
| **Cisco Systems** (cisco) | 6-Milestone End-of-Life Policy | `End-of-Life Announcement Date` | Official bulletin published detailing the entire lifecycle timeline. |
| **Cisco Systems** (cisco) | 6-Milestone End-of-Life Policy | `End-of-Sale Date (EoS)` | Last date to order the product through standard Cisco sales channels. |
| **Cisco Systems** (cisco) | 6-Milestone End-of-Life Policy | `End of SW Maintenance Releases` | Final software release for maintenance bug fixes and maintenance releases. |
| **Cisco Systems** (cisco) | 6-Milestone End-of-Life Policy | `End of Vulnerability/Security Support` | Final security and vulnerability patches released. |
| **Cisco Systems** (cisco) | 6-Milestone End-of-Life Policy | `End of Routine Failure Analysis` | Last date hardware engineering will diagnose operational failures. |
| **Cisco Systems** (cisco) | 6-Milestone End-of-Life Policy | `Last Date of Support (LDoS)` | Final date to receive service contracts, parts replacement, and TAC assistance. |
| **Citrix Systems** (citrix) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Commvault** (commvault) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **D-Link** (dlink) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Dell Technologies** (dell) | PowerEdge & PowerStore Lifecycle | `Active` | Current generation in standard distribution. |
| **Dell Technologies** (dell) | PowerEdge & PowerStore Lifecycle | `End of Standard Support (EoSS)` | Standard 3/5-year ProSupport warranty expires. |
| **Dell Technologies** (dell) | PowerEdge & PowerStore Lifecycle | `End of Service Life (EOSL)` | All maintenance, parts, and engineering updates discontinued. |
| **Extreme Networks** (extreme_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **F5 Networks** (f5_networks) | BIG-IP & Hardware Lifecycle | `End of Sale (EoS)` | BIG-IP appliance ordering concludes. |
| **F5 Networks** (f5_networks) | BIG-IP & Hardware Lifecycle | `End of Software Development (EoSD)` | TMOS maintenance releases frozen. |
| **F5 Networks** (f5_networks) | BIG-IP & Hardware Lifecycle | `End of Support (EoS)` | Complete hardware/software support cutoff. |
| **Fluke Networks** (fluke_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Fortinet** (fortinet) | FortiGate Product Lifecycle | `End of Order (EOO)` | Last day product hardware can be ordered. |
| **Fortinet** (fortinet) | FortiGate Product Lifecycle | `Last Time Buy (LTB)` | Final delivery cutoff. |
| **Fortinet** (fortinet) | FortiGate Product Lifecycle | `End of Engineering Support (EOES)` | FortiOS maintenance releases and vulnerability patches frozen. |
| **Fortinet** (fortinet) | FortiGate Product Lifecycle | `End of Support (EOS)` | Complete technical TAC support retired. |
| **Hewlett Packard Enterprise** (hpe) | ProLiant & Aruba 3-Milestone Lifecycle | `Active` | Standard commercial availability and full warranty support. |
| **Hewlett Packard Enterprise** (hpe) | ProLiant & Aruba 3-Milestone Lifecycle | `End of Sale (EOS)` | Commercial sales window closed; server or switch no longer orderable. |
| **Hewlett Packard Enterprise** (hpe) | ProLiant & Aruba 3-Milestone Lifecycle | `End of Engineering Support (EOES)` | Firmware, SPP updates, and driver maintenance conclude. |
| **Hewlett Packard Enterprise** (hpe) | ProLiant & Aruba 3-Milestone Lifecycle | `End of Service Life (EOSL)` | Complete termination of hardware support and maintenance contracts. |
| **Huawei** (huawei) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **IBM Systems** (ibm) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Juniper Networks** (juniper) | Junos & Hardware EOL Milestones | `End of Life Announcement (EOA)` | Notice published. |
| **Juniper Networks** (juniper) | Junos & Hardware EOL Milestones | `End of Sale (EOS)` | Last order date. |
| **Juniper Networks** (juniper) | Junos & Hardware EOL Milestones | `End of Engineering (EOE)` | Junos bug fix freeze. |
| **Juniper Networks** (juniper) | Junos & Hardware EOL Milestones | `End of Support (EOS)` | TAC contract expiration. |
| **Lenovo** (lenovo) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Microsoft** (microsoft) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **NETGEAR Business** (netgear_business) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **NetApp Storage Systems** (netapp) | ONTAP & Storage Lifecycle | `Available` | Active storage array. |
| **NetApp Storage Systems** (netapp) | ONTAP & Storage Lifecycle | `End of Availability` | Final order window. |
| **NetApp Storage Systems** (netapp) | ONTAP & Storage Lifecycle | `End of Support (EOS)` | Self-service / best-effort support only. |
| **Nutanix HCI** (nutanix) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Oracle** (oracle) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Palo Alto Networks** (palo_alto) | PAN-OS Hardware & Software Lifecycle | `End-of-Sale (EoS)` | Hardware firewall or software subscription no longer available for purchase. |
| **Palo Alto Networks** (palo_alto) | PAN-OS Hardware & Software Lifecycle | `End-of-Engineering (EoE)` | PAN-OS maintenance releases and software patches cease. |
| **Palo Alto Networks** (palo_alto) | PAN-OS Hardware & Software Lifecycle | `End-of-Life (EoL)` | All technical support and TAC access expire. |
| **Pure Storage** (pure_storage) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **QNAP Systems** (qnap) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Red Hat Enterprise** (red_hat) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Ruckus Networks (CommScope)** (ruckus_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **SUSE Linux Enterprise** (suse) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **SonicWall Security** (sonicwall) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Sophos Cybersecurity** (sophos) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Supermicro** (supermicro) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Synology NAS & Enterprise** (synology) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **TP-Link** (tplink) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Trend Micro** (trend_micro) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Ubiquiti Inc.** (ubiquiti) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **VMware** (vmware) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **WatchGuard Technologies** (watchguard) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Westermo Network Technologies** (westermo) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
| **Zyxel Networks** (zyxel_networks) | Standard Multi-Stage | `Active` / `Phase-Out (LTB)` / `Discontinued` / `End of Support (EOS)` | Full lifecycle tracking: active ordering, last-time buy notices, parts transition, and complete support retirement. |
