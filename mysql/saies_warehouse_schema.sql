-- SAIES Control Tower warehouse schema for MySQL 8+
-- Production-oriented DDL matching the SQLite warehouse built by etl_star_schema.py.

CREATE DATABASE IF NOT EXISTS `saies_warehouse`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

USE `saies_warehouse`;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `fact_carbon`;
DROP TABLE IF EXISTS `fact_pricing`;
DROP TABLE IF EXISTS `fact_sales`;
DROP TABLE IF EXISTS `dim_emission_scope`;
DROP TABLE IF EXISTS `dim_emission_type`;
DROP TABLE IF EXISTS `dim_simulation`;
DROP TABLE IF EXISTS `dim_date`;
DROP TABLE IF EXISTS `dim_sales_org`;
DROP TABLE IF EXISTS `dim_customer`;
DROP TABLE IF EXISTS `dim_location`;
DROP TABLE IF EXISTS `dim_product`;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE `dim_product` (
  `product_key` INT NOT NULL AUTO_INCREMENT,
  `MATERIAL_NUMBER` VARCHAR(30) NOT NULL,
  `MATERIAL_DESCRIPTION` VARCHAR(100),
  `MATERIAL_TYPE` VARCHAR(30),
  `MATERIAL_CODE` VARCHAR(30),
  `MATERIAL_LABEL` VARCHAR(100),
  PRIMARY KEY (`product_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Product/material dimension';

CREATE TABLE `dim_location` (
  `location_key` INT NOT NULL AUTO_INCREMENT,
  `STORAGE_LOCATION` VARCHAR(30) NOT NULL,
  `REGION` VARCHAR(60),
  `AREA` VARCHAR(60),
  `CITY` VARCHAR(100),
  `COUNTRY` VARCHAR(100),
  `POSTAL_CODE` INT,
  PRIMARY KEY (`location_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Storage location and geography dimension';

CREATE TABLE `dim_customer` (
  `customer_key` INT NOT NULL AUTO_INCREMENT,
  `CUSTOMER_NUMBER` INT NOT NULL,
  `DISTRIBUTION_CHANNEL` INT NOT NULL,
  PRIMARY KEY (`customer_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Customer and distribution channel dimension';

CREATE TABLE `dim_sales_org` (
  `sales_org_key` INT NOT NULL AUTO_INCREMENT,
  `SALES_ORGANIZATION` VARCHAR(20) NOT NULL,
  PRIMARY KEY (`sales_org_key`),
  UNIQUE KEY `uq_dim_sales_org_code` (`SALES_ORGANIZATION`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Sales organization/company code dimension';

CREATE TABLE `dim_date` (
  `date_key` INT NOT NULL AUTO_INCREMENT,
  `SIM_CALENDAR_DATE` DATE NOT NULL,
  `SIM_DATE` VARCHAR(10) NOT NULL,
  `SIM_PERIOD` INT NOT NULL,
  `calendar_date` DATE NOT NULL,
  `year` INT NOT NULL,
  `quarter` INT NOT NULL,
  `quarter_name` VARCHAR(2) NOT NULL,
  `month_number` INT NOT NULL,
  `month_name` VARCHAR(20) NOT NULL,
  `month_abbrev` VARCHAR(3) NOT NULL,
  `week_number` INT NOT NULL,
  `day_of_month` INT NOT NULL,
  `day_of_week` INT NOT NULL,
  `day_name` VARCHAR(20) NOT NULL,
  `is_weekend` TINYINT NOT NULL,
  `is_month_start` TINYINT NOT NULL,
  `is_month_end` TINYINT NOT NULL,
  `is_quarter_end` TINYINT NOT NULL,
  `is_year_end` TINYINT NOT NULL,
  PRIMARY KEY (`date_key`),
  UNIQUE KEY `uq_dim_date_calendar` (`SIM_CALENDAR_DATE`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Calendar dimension with ERPSIM simulation date attributes';

CREATE TABLE `dim_simulation` (
  `sim_key` INT NOT NULL AUTO_INCREMENT,
  `SIM_ROUND` INT NOT NULL,
  `SIM_STEP` INT NOT NULL,
  `SIM_ELAPSED_STEPS` INT NOT NULL,
  PRIMARY KEY (`sim_key`),
  UNIQUE KEY `uq_dim_simulation_step` (`SIM_ROUND`, `SIM_STEP`, `SIM_ELAPSED_STEPS`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='ERPSIM simulation coordinate dimension';

CREATE TABLE `dim_emission_type` (
  `emission_type_key` INT NOT NULL AUTO_INCREMENT,
  `TYPE` VARCHAR(60) NOT NULL,
  `SUBTYPE` VARCHAR(100) NOT NULL,
  PRIMARY KEY (`emission_type_key`),
  UNIQUE KEY `uq_dim_emission_type` (`TYPE`, `SUBTYPE`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Carbon emission type and subtype dimension';

CREATE TABLE `dim_emission_scope` (
  `scope_key` INT NOT NULL AUTO_INCREMENT,
  `SCOPE` INT NOT NULL,
  `SCOPE_NAME` VARCHAR(60) NOT NULL,
  PRIMARY KEY (`scope_key`),
  UNIQUE KEY `uq_dim_emission_scope` (`SCOPE`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Carbon accounting scope dimension';

CREATE TABLE `fact_sales` (
  `product_key` INT NOT NULL,
  `location_key` INT NOT NULL,
  `customer_key` INT NOT NULL,
  `sales_org_key` INT NOT NULL,
  `date_key` INT NOT NULL,
  `sim_key` INT NOT NULL,
  `ROW_ID` INT NOT NULL,
  `SALES_ORDER_NUMBER` BIGINT,
  `LINE_ITEM` INT,
  `QUANTITY` DECIMAL(14,4),
  `QUANTITY_DELIVERED` DECIMAL(14,4),
  `UNIT` VARCHAR(20),
  `NET_PRICE` DECIMAL(14,4),
  `NET_VALUE` DECIMAL(14,4),
  `COST` DECIMAL(14,4),
  `CURRENCY` VARCHAR(10),
  `CONTRIBUTION_MARGIN` DECIMAL(14,4),
  `CONTRIBUTION_MARGIN_PCT` DECIMAL(12,6),
  PRIMARY KEY (`ROW_ID`),
  KEY `idx_fact_sales_product_key` (`product_key`),
  KEY `idx_fact_sales_location_key` (`location_key`),
  KEY `idx_fact_sales_customer_key` (`customer_key`),
  KEY `idx_fact_sales_sales_org_key` (`sales_org_key`),
  KEY `idx_fact_sales_date_key` (`date_key`),
  KEY `idx_fact_sales_sim_key` (`sim_key`),
  CONSTRAINT `fk_fact_sales_product` FOREIGN KEY (`product_key`) REFERENCES `dim_product` (`product_key`),
  CONSTRAINT `fk_fact_sales_location` FOREIGN KEY (`location_key`) REFERENCES `dim_location` (`location_key`),
  CONSTRAINT `fk_fact_sales_customer` FOREIGN KEY (`customer_key`) REFERENCES `dim_customer` (`customer_key`),
  CONSTRAINT `fk_fact_sales_sales_org` FOREIGN KEY (`sales_org_key`) REFERENCES `dim_sales_org` (`sales_org_key`),
  CONSTRAINT `fk_fact_sales_date` FOREIGN KEY (`date_key`) REFERENCES `dim_date` (`date_key`),
  CONSTRAINT `fk_fact_sales_sim` FOREIGN KEY (`sim_key`) REFERENCES `dim_simulation` (`sim_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Fact grain: one row per sales order line item';

CREATE TABLE `fact_pricing` (
  `product_key` INT NOT NULL,
  `sales_org_key` INT NOT NULL,
  `date_key` INT NOT NULL,
  `sim_key` INT NOT NULL,
  `ROW_ID` INT NOT NULL,
  `DISTRIBUTION_CHANNEL` INT,
  `DC_NAME` VARCHAR(100),
  `PRICE` DECIMAL(14,4),
  `CURRENCY` VARCHAR(10),
  PRIMARY KEY (`ROW_ID`),
  KEY `idx_fact_pricing_product_key` (`product_key`),
  KEY `idx_fact_pricing_sales_org_key` (`sales_org_key`),
  KEY `idx_fact_pricing_date_key` (`date_key`),
  KEY `idx_fact_pricing_sim_key` (`sim_key`),
  CONSTRAINT `fk_fact_pricing_product` FOREIGN KEY (`product_key`) REFERENCES `dim_product` (`product_key`),
  CONSTRAINT `fk_fact_pricing_sales_org` FOREIGN KEY (`sales_org_key`) REFERENCES `dim_sales_org` (`sales_org_key`),
  CONSTRAINT `fk_fact_pricing_date` FOREIGN KEY (`date_key`) REFERENCES `dim_date` (`date_key`),
  CONSTRAINT `fk_fact_pricing_sim` FOREIGN KEY (`sim_key`) REFERENCES `dim_simulation` (`sim_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Fact grain: one product/channel/date price condition';

CREATE TABLE `fact_carbon` (
  `sales_org_key` INT NOT NULL,
  `date_key` INT NOT NULL,
  `sim_key` INT NOT NULL,
  `emission_type_key` INT NOT NULL,
  `scope_key` INT NOT NULL,
  `ROW_ID` INT NOT NULL,
  `ORIGIN` VARCHAR(30),
  `DESTINATION` VARCHAR(30),
  `PRODUCT` VARCHAR(30),
  `MATERIAL_DOCUMENT` BIGINT,
  `EMISSIONS` DECIMAL(14,4),
  `TOTAL_CO2E_EMISSIONS` DECIMAL(14,4),
  PRIMARY KEY (`ROW_ID`),
  KEY `idx_fact_carbon_sales_org_key` (`sales_org_key`),
  KEY `idx_fact_carbon_date_key` (`date_key`),
  KEY `idx_fact_carbon_sim_key` (`sim_key`),
  KEY `idx_fact_carbon_emission_type_key` (`emission_type_key`),
  KEY `idx_fact_carbon_scope_key` (`scope_key`),
  CONSTRAINT `fk_fact_carbon_sales_org` FOREIGN KEY (`sales_org_key`) REFERENCES `dim_sales_org` (`sales_org_key`),
  CONSTRAINT `fk_fact_carbon_date` FOREIGN KEY (`date_key`) REFERENCES `dim_date` (`date_key`),
  CONSTRAINT `fk_fact_carbon_sim` FOREIGN KEY (`sim_key`) REFERENCES `dim_simulation` (`sim_key`),
  CONSTRAINT `fk_fact_carbon_emission_type` FOREIGN KEY (`emission_type_key`) REFERENCES `dim_emission_type` (`emission_type_key`),
  CONSTRAINT `fk_fact_carbon_scope` FOREIGN KEY (`scope_key`) REFERENCES `dim_emission_scope` (`scope_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
COMMENT='Fact grain: one carbon emissions activity event';
