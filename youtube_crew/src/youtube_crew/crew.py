from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
import os
from youtube_crew.tools import GetNextOpenLinkTool, AmazonBestsellerScraperTool, ComfyUIVideoTool, EdgeTTSTool, VideoFusionTool, YouTubeUploaderTool, AmazonContentScrapeTool

@CrewBase
class YoutubeCrew():
    """YoutubeCrew crew"""

    agents: list[Agent]
    tasks: list[Task]

    openrouter_llm = LLM(
        model="openrouter/google/gemini-2.0-flash-lite-001",
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    @agent
    def link_manager(self) -> Agent:
        return Agent(
            config=self.agents_config['link_manager'],
            verbose=True,
            llm=self.openrouter_llm,
            tools=[GetNextOpenLinkTool(), AmazonBestsellerScraperTool()],
        )

    @agent
    def data_processor(self) -> Agent:
        return Agent(
            config=self.agents_config['data_processor'], # type: ignore[index]
            verbose=True,
            llm=self.openrouter_llm,
            tools=[AmazonContentScrapeTool()],
        )

    @agent
    def short_script_expert(self) -> Agent:
        return Agent(
            config=self.agents_config['short_script_expert'],
            llm=self.openrouter_llm,
            verbose=True
        )

    @agent
    def tts_narration_expert(self) -> Agent:
        return Agent(
            config=self.agents_config['tts_narration_expert'],
            llm=self.openrouter_llm,
            tools=[EdgeTTSTool()],
            verbose=True,
        )
    
    @agent
    def video_production_assistant(self) -> Agent:
        return Agent(
            config=self.agents_config['video_production_assistant'],
            llm=self.openrouter_llm,
            tools=[ComfyUIVideoTool()],
            verbose=True,
            allow_delegation=False
        )

    @agent
    def fusion_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['fusion_agent'],
            llm=self.openrouter_llm,
            tools=[VideoFusionTool()],
            verbose=True,
            allow_delegation=False,
        )

    @agent
    def youtube_uploader_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['youtube_uploader_agent'],
            llm=self.openrouter_llm,
            tools=[YouTubeUploaderTool()],
            verbose=True,
            allow_delegation=False,
        )
    
    @task
    def manage_link_queue(self) -> Task:
        return Task(
            config=self.tasks_config['manage_link_queue'],
        )
    
    @task
    def extract_product_data(self) -> Task:
        return Task(
            config=self.tasks_config['extract_product_data'],
            output_file='latest_product_data.md'
        )

    @task
    def create_shorts_script_task(self) -> Task:
        return Task(
            config=self.tasks_config['create_shorts_script_task'],
            output_file='youtube_short.md'
        )
    

    @task
    def create_tts_audio_task(self) -> Task:
        return Task(
            config=self.tasks_config['create_tts_audio_task'],
            output_file='youtube_short_tts.md',
        )
    
    @task
    def generate_video_clips_task(self) -> Task:
        return Task(
            config=self.tasks_config['generate_video_clips_task'],
            output_file='youtube_video.md',
        )

    @task
    def fuse_video_task(self) -> Task:
        return Task(
            config=self.tasks_config['fuse_video_task'],
            output_file='youtube_final_video.md',
        )

    @task
    def upload_youtube_video_task(self) -> Task:
        return Task(
            config=self.tasks_config['upload_youtube_video_task'],
            output_file='youtube_upload.md',
        )

    @crew
    def crew(self) -> Crew:
        """Creates the YoutubeCrew crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

        return Crew(
            agents=[
                self.link_manager(),
                self.data_processor(),
                self.short_script_expert(),
                self.tts_narration_expert(),
                self.video_production_assistant(),
                self.fusion_agent(),
                self.youtube_uploader_agent(),
            ],
            tasks=[
                self.manage_link_queue(),
                self.extract_product_data(),
                self.create_shorts_script_task(),
                self.create_tts_audio_task(),
                self.generate_video_clips_task(),
                self.fuse_video_task(),
                self.upload_youtube_video_task(),
            ],
            process=Process.sequential,
            verbose=True,
            # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )
