// hubspot.js

import {useState, useEffect} from 'react';
import {
    Box,
    Button,
    CircularProgress
} from '@mui/material'
import axios from 'axios'

export const HubspotIntegration = ({user, org, integrationParams, setIntegrationParams}) =>{
    const [isConnected, setIsConnected] = useState(false);
    const [isConnecting, setIsConnecting] = useState(false);
    const [data, setData] = useState([]);

    const handleConnectClick = async () =>{
        try{
            setIsConnecting(true);
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);
            const response = await axios.post('http://localhost:8000/integrations/hubspot/authorize', formData);
            const authURL = response?.data;
            const newWindow = window.open(authURL, 'Hubspot Authorization', 'width=600, height=600');

            const pollTimer = window.setInterval(() => {
                if (newWindow?.closed !== false){
                    window.clearInterval(pollTimer);
                    handleWindowClosed();
                }
            }, 200);
        } catch (e) {
            setIsConnecting(false);
            alert(e?.response?.data?.detail);
        }
    }

    const handleWindowClosed = async () =>{
        try {
            const formData = new FormData();
            formData.append('user_id', user);
            formData.append('org_id', org);
            const response = await axios.post('http://localhost:8000/integrations/hubspot/credentials', formData);
            const credentials = response.data;
            if (credentials){
                setIsConnecting(false);
                setIsConnected(true);
                setIntegrationParams(prev => ({...prev, credentials: credentials, type: 'Hubspot'}));
                await loadData(credentials);
            }
            setIsConnecting(false);
        } catch (e) {
            setIsConnecting(false);
            alert(e?.response?.data?.detail);
        }
    }

    const loadData = async (credentials) => {
    try {
        const formData = new FormData();
        formData.append("credentials", JSON.stringify(credentials));
        const response = await axios.post("http://localhost:8000/integrations/hubspot/get_hubspot_items", formData);
        setData(response.data);
    } catch (e) {
        console.error(e);
        alert("Failed to load data");
    }
    }
    console.log("Final list of items:", data);
    useEffect(() =>{
        setIsConnected(integrationParams?.credentials ? true : false)
    }, []);

    

    return (
        <>
        <Box sx={{mt: 2}}>
            Parameters
            <Box display='flex' alignItems='center' justifyContent='center' sx={{mt: 2}}>
                <Button
                    variant='contained'
                    onClick={isConnected ? () => {} :handleConnectClick}
                    color={isConnected ? 'success' : 'primary'}
                    disabled = {isConnecting}
                    style={{
                        pointerEvents: isConnected ? 'none' : 'auto',
                        cursor: isConnected ? 'default' : 'pointer',
                        opacity: isConnected ? 1 : undefined
                    }}>
                        {isConnected ? 'Hubspot Connected': isConnecting ? <CircularProgress size={20}/> : 'connect to Hubsot'}
                    </Button>
            </Box>
                
        </Box>
        
        </>
    );

}