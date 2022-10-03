"""Config flow for XY Screens integration."""
from __future__ import annotations

import logging
import os
from typing import Any

import serial
import serial.tools.list_ports
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_MANUAL_PATH,
    CONF_SERIAL_PORT,
    CONF_TIME_CLOSE,
    CONF_TIME_OPEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class XYScreensConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for XY Screens."""

    VERSION = 1

    STEP_SETUP_SERIAL_SCHEMA = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_setup_serial(user_input)

    async def async_step_setup_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the setup serial step."""
        errors: dict[str, str] = {}

        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        list_of_ports = {}
        for port in ports:
            list_of_ports[
                port.device
            ] = f"{port}, s/n: {port.serial_number or 'n/a'}" + (
                f" - {port.manufacturer}" if port.manufacturer else ""
            )

        self.STEP_SETUP_SERIAL_SCHEMA = vol.Schema(
            {
                vol.Exclusive(CONF_SERIAL_PORT, CONF_SERIAL_PORT): vol.In(
                    list_of_ports
                ),
                vol.Exclusive(
                    CONF_MANUAL_PATH, CONF_SERIAL_PORT, CONF_MANUAL_PATH
                ): cv.string,
                vol.Required(CONF_TIME_OPEN): cv.positive_int,
                vol.Required(CONF_TIME_CLOSE): cv.positive_int,
            }
        )

        if user_input is not None:
            try:
                info = await self.validate_input_setup_serial(user_input, errors)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception: %s", ex)
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=info)

        return self.async_show_form(
            step_id="setup_serial",
            data_schema=self.STEP_SETUP_SERIAL_SCHEMA,
            errors=errors,
        )

    async def validate_input_setup_serial(
        self, data: dict[str, Any], errors: dict[str, str]
    ) -> dict[str, Any]:
        """Validate the user input allows us to connect.

        Data has the keys from STEP_SETUP_SERIAL_SCHEMA with values provided by the user.
        """
        # Validate the data can be used to set up a connection.
        self.STEP_SETUP_SERIAL_SCHEMA(data)

        serial_port = None
        if CONF_MANUAL_PATH in data:
            serial_port = data[CONF_MANUAL_PATH]
        elif CONF_SERIAL_PORT in data:
            serial_port = data[CONF_SERIAL_PORT]

        if serial_port is None:
            raise vol.error.RequiredFieldInvalid()

        serial_port = await self.hass.async_add_executor_job(
            get_serial_by_id, serial_port
        )

        # Test if the device exists
        if not os.path.exists(serial_port):
            raise vol.error.PathInvalid(
                f"Device {serial_port} does not exists"
            )

        await self.async_set_unique_id(serial_port)
        self._abort_if_unique_id_configured()

        # Test if we can connect to the device.
        try:
            # Create the connection instance.
            connection = serial.Serial(
                port=serial_port,
                baudrate=2400,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
            )

            # Open the connection.
            if not connection.is_open:
                connection.open()

            # Close the connection.
            connection.close()

            _LOGGER.info("Device %s available", serial_port)
        except serial.SerialException as ex:
            raise CannotConnect(f"Unable to connect to the device {serial_port}: {ex}", ex)

        # Return info that you want to store in the config entry.
        return {
            "title": f"XY Screens {serial_port}",
            CONF_SERIAL_PORT: serial_port,
            CONF_TIME_OPEN: data[CONF_TIME_OPEN],
            CONF_TIME_CLOSE: data[CONF_TIME_CLOSE],
        }


def get_serial_by_id(dev_path: str) -> str:
    """Return a /dev/serial/by-id match for given device if available."""
    by_id = "/dev/serial/by-id"
    if not os.path.isdir(by_id):
        return dev_path

    for path in (entry.path for entry in os.scandir(by_id) if entry.is_symlink()):
        if os.path.realpath(path) == dev_path:
            return path
    return dev_path


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
