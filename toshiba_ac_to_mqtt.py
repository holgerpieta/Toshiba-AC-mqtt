# Copyright 2021 Holger Pieta

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
logging.basicConfig(format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel( logging.INFO )
mqtt_logger = logging.getLogger("MQTT")
mqtt_logger.setLevel( logging.INFO )

import asyncio
import json
import platform
import contextlib
import asyncio_mqtt

from toshiba_ac.device_manager import ToshibaAcDeviceManager
from toshiba_ac.fcu_state import ToshibaAcFcuState

mqtt_server = 'your-mqtt-server'
topic_root = 'ac'
status_suffix = 'status'
status_topic = topic_root + '/' + status_suffix
cmd_suffix = 'cmd'
cmd_topic = topic_root + '/' + cmd_suffix
power_suffix = 'power'
online_payload = 'online'
offline_payload = 'offline'
ac_username = 'Your-Toshiba-Username'
ac_password = 'Your-Toshiba-Password'

# Task for device specific commands
async def handle_ac_device_cmd( messages, dev ):
    async for msg in messages:
        logger.info( f'Command for AC {dev.name}: {msg.payload}' )
        new_state = ToshibaAcFcuState.from_dict_state( json.loads( msg.payload ) )
        await dev.send_state_to_ac( new_state )

# Energy updates should not happen
async def energy_changed( dev ):
    logger.error( 'Received energy update for device %s, this should not happen!' % dev)

# Log a warning for messages received on unhandled topics
async def log_unfiltered_message( messages ):
    async for msg in messages:
        mqtt_logger.warning( f'Unexpected message received on topic "{msg.topic}": {str(msg.payload)}' )

async def cancel_tasks( tasks ):
    # Nothing to do if tasks is empty
    if not tasks:
        logger.debug( f'No tasks to cancel.' )
        return
    # Cancel all tasks
    logger.debug( f'Cancelling all tasks' )
    for task in tasks:
        task.cancel()
    # Wait for 60 seconds for all tasks to finish (get cancelled)
    logger.debug( f'Waiting for tasks to finish' )
    await asyncio.wait( tasks, timeout = 60 )
    # List of all task results
    res = []
    # Check all tasks
    for task in tasks:
        try:
            # Check results of task
            res.append( task.result() )
        except asyncio.InvalidStateError as err:
            # Task did not finish, so log a problem
            logger.error( f'Task not cancelled in 60 seconds: {task.get_name()}' )
            # Return the InvalidStateError
            res.append( err )
        except asyncio.CancelledError as err:
            # Task was cancelled, so return the CancelledError
            res.append( err )
        except Exception as err:
            # Task failed, so log and return the exception
            logger.error( f'Exception occured in cancelled task {task.get_name()}')
            logger.exception( err )
            res.append( err )
    # Return results of tasks that finished in time.
    return res

async def mqtt_ac_task():
    async with contextlib.AsyncExitStack() as stack:
        # List of tasks we create to track them later
        tasks = []
        # Register callback to cancel all tasks if something goes wrong.
        stack.push_async_callback( cancel_tasks, tasks )
        # Define last will
        will = asyncio_mqtt.Will( status_topic, offline_payload, 2, True )
        # Connect to the MQTT broker
        client = asyncio_mqtt.Client( mqtt_server, logger=mqtt_logger, will=will )
        logger.debug( 'Connecting MQTT' )
        await stack.enter_async_context( client )
        # Register offline message callback
        stack.push_async_callback( client.publish, status_topic, offline_payload, 2, True )
        # Publish online message
        await client.publish( status_topic, online_payload, 2, True )
        # Start task to handle otherwise unhandled topics
        logger.debug( 'Registering unfiltered messages' )
        unfiltered_messages = await stack.enter_async_context( client.unfiltered_messages() )
        logger.debug( 'Starting task for unfiltered messages' )
        tasks.append( asyncio.create_task( log_unfiltered_message( unfiltered_messages ) ) )

        # Create AC device manager
        loop = asyncio.get_running_loop()
        device_manager = ToshibaAcDeviceManager( loop, ac_username, ac_password, use_power=True )
        # Register shutdown callback
        stack.push_async_callback( device_manager.shutdown )
        # Connect to AC device manager
        await device_manager.connect()

        # Send updated power to MQTT
        async def power_changed( dev ):
            logger.debug( 'Power changed for device %s' % dev)
            topic = f'{topic_root}/{dev.name}/{power_suffix}'
            msg = json.dumps( {'Name': dev.name, 'Power': dev.ac_power})
            logger.debug( f'Sending MQTT power update with topic {topic}: {msg}' )
            await client.publish( topic, msg, 2 )

        # Send updated state to MQTT
        async def state_update( dev, state ):
            topic = f'{topic_root}/{dev.name}/{status_suffix}'
            state_flt = state.forJson()
            if state_flt:
                msg = json.dumps( { 'Name': dev.name, 'Status': state_flt } )
                logger.debug( f'Sending MQTT status update with topic {topic}: {msg}' )
                await client.publish( topic, msg, 2 )
            else:
                logger.info( f'Not sending empty state update on topic {topic}' )

        # Callback for state updates
        async def state_changed( dev ):
            logger.debug( 'State changed for device %s' % dev)
            await state_update( dev, dev.fcu_state_delta )

        # Get all connected AC devices
        devices = await device_manager.get_devices()
        tasks.append( device_manager.periodic_fetch_energy_consumption_task )
        # Connect each device and register callbacks
        for device in devices:
            tasks.append( device.periodic_reload_state_task )
            device.on_state_changed_callback.add( state_changed )
            await device.state_changed()
            device.on_energy_consumption_changed_callback.add( energy_changed )
            device.on_power_changed_callback.add( power_changed )
            # Start task to handle device specific commands
            topic = f'{topic_root}/{device.name}/{cmd_suffix}'
            logger.debug( f'Registering {topic} messages' )
            ac_dev_cmd_messages = await stack.enter_async_context( client.filtered_messages( topic ) )
            logger.debug( f'Starting task for {topic} messages' )
            tasks.append( asyncio.create_task( handle_ac_device_cmd( ac_dev_cmd_messages, device ) ) )
            # Subscribe to cmd_topic
            logger.debug( f'Subscribing to {topic}' )
            await client.subscribe( topic )

        # Send states of all devices
        async def state_update_all_dev( devices ):
            for dev in devices:
                    logger.debug( 'Sending regular state update for device %s' % dev)
                    await state_update( dev, dev.fcu_state )

        # Handle general commands
        async def handle_ac_cmd( messages, devices ):
            async for msg in messages:
                if msg.payload.decode() == 'status':
                    await state_update_all_dev( devices )
                else:
                    mqtt_logger.warning( f'Not implemented: Message received on topic "{msg.topic}": {str(msg.payload)}' )

        # Start task to handle cmd_topic messages
        logger.debug( f'Registering {cmd_topic} messages' )
        ac_cmd_messages = await stack.enter_async_context( client.filtered_messages( cmd_topic ) )
        logger.debug( f'Starting task for {cmd_topic} messages' )
        tasks.append( asyncio.create_task( handle_ac_cmd( ac_cmd_messages, devices ) ) )
        # Subscribe to cmd_topic
        logger.debug( f'Subscribing to {cmd_topic}' )
        await client.subscribe( cmd_topic )

        # Task for regular state updates
        async def regular_state_update( devices ):
            while True:
                delay = 60 * 60
                logger.debug( f'Regular state update sleeping for {delay} seconds.')
                await asyncio.sleep( delay )
                await state_update_all_dev( devices )

        tasks.append( asyncio.create_task( regular_state_update( devices ) ) )

        # Monitor all tasks we've created
        logger.debug( 'Monitoring tasks' )
        done, pending = await asyncio.wait( tasks, return_when = asyncio.FIRST_COMPLETED )
        logger.warning( 'At least one task crashed.' )
        done.pop().result()
        logger.debug( 'mqtt_ac_task finished.' )

async def main():
    # Create a coroutine group and run it
    await mqtt_ac_task()

if __name__ == '__main__':
    # Asyncio MQTT needs a special event loop on windows.
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy( asyncio.WindowsSelectorEventLoopPolicy() )
    asyncio.run( main() )
